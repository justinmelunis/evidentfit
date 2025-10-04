"""
Get Papers Pipeline - Main orchestration

Orchestrates the complete get_papers flow: search → fetch → parse → score → select → save.
No LLM calls - pure rule-based processing with diversity filtering.
"""

import os
import sys
import time
import argparse
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the parent directory to the path so we can import from get_papers
sys.path.insert(0, str(Path(__file__).parent.parent))

from get_papers.pubmed_client import multi_supplement_search, pubmed_efetch_xml, pubmed_esearch, PM_SEARCH_QUERY
from get_papers.parsing import parse_pubmed_article
from get_papers.diversity import (
    analyze_combination_distribution, 
    calculate_combination_weights, 
    calculate_combination_score,
    iterative_diversity_filtering,
    should_run_iterative_diversity
)
from get_papers.storage import save_selected_papers, save_run_metadata, create_metadata_summary

logger = logging.getLogger(__name__)

# Environment variables with defaults
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT", "50000"))
MAX_TOTAL_PAPERS = int(os.getenv("MAX_TOTAL_PAPERS", "200000"))
DIVERSITY_ROUNDS_THRESHOLD = int(os.getenv("DIVERSITY_ROUNDS_THRESHOLD", "50000"))
QUALITY_FLOOR_BOOTSTRAP = float(os.getenv("QUALITY_FLOOR_BOOTSTRAP", "3.0"))
QUALITY_FLOOR_MONTHLY = float(os.getenv("QUALITY_FLOOR_MONTHLY", "2.5"))
WATERMARK_KEY = os.getenv("WATERMARK_KEY", "meta:last_ingest")


def setup_logging() -> logging.Logger:
    """Setup logging for the pipeline"""
    log_level = os.getenv("LOG_LEVEL", "info").upper()
    log_level = getattr(logging, log_level, logging.INFO)
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/get_papers_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Get Papers Pipeline - Logging initialized")
    logger.info(f"Level: {log_level}, File: {log_file}")
    return logger


def get_watermark_mindate() -> Optional[str]:
    """
    Get mindate from watermark (for monthly mode)
    
    Returns:
        Mindate string in YYYY/MM/DD format or None
    """
    # For now, we'll implement a simple local watermark check
    # In a full implementation, this would check Azure Search for the watermark doc
    watermark_file = Path("data/ingest/raw/watermark.json")
    if watermark_file.exists():
        try:
            import json
            with open(watermark_file, 'r') as f:
                watermark_data = json.load(f)
            last_ingest_iso = watermark_data.get("last_ingest_iso")
            if last_ingest_iso:
                dt = datetime.datetime.fromisoformat(last_ingest_iso.replace("Z", "+00:00"))
                return dt.strftime("%Y/%m/%d")
        except Exception as e:
            logger.warning(f"Could not read watermark: {e}")
    
    return None


def update_watermark() -> None:
    """Update local watermark with current timestamp"""
    watermark_file = Path("data/ingest/raw/watermark.json")
    watermark_file.parent.mkdir(parents=True, exist_ok=True)
    
    now_iso = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    watermark_data = {
        "last_ingest_iso": now_iso,
        "updated_at": now_iso
    }
    
    import json
    with open(watermark_file, 'w') as f:
        json.dump(watermark_data, f, indent=2)
    
    logger.info(f"Watermark updated to {now_iso}")


def fetch_papers(mode: str, limit: Optional[int] = None) -> List[str]:
    """
    Fetch PMIDs based on mode
    
    Args:
        mode: 'bootstrap' or 'monthly'
        limit: Optional limit on number of PMIDs
        
    Returns:
        List of PMIDs
    """
    if mode == "bootstrap":
        logger.info("Bootstrap mode: Using multi-supplement search for comprehensive coverage...")
        mindate = "1990/01/01"  # Comprehensive historical evaluation
        ids = multi_supplement_search(mindate=mindate)
        logger.info(f"Bootstrap: Found {len(ids)} PMIDs from multi-supplement search")
    else:
        # Monthly mode
        mindate = get_watermark_mindate()
        if not mindate:
            logger.warning("No watermark found, using 30 days ago as fallback")
            thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
            mindate = thirty_days_ago.strftime("%Y/%m/%d")
        
        logger.info(f"Monthly mode: Searching for papers since {mindate}")
        ids = []
        retstart = 0
        
        while len(ids) < 3000:  # Reasonable limit for monthly updates
            batch = pubmed_esearch(PM_SEARCH_QUERY, mindate=mindate, retmax=200, retstart=retstart)
            idlist = batch.get("esearchresult", {}).get("idlist", [])
            if not idlist:
                break
            ids.extend(idlist)
            retstart += len(idlist)
            if retstart >= int(batch["esearchresult"].get("count", "0")):
                break
            time.sleep(1.0)  # Rate limiting
        
        logger.info(f"Monthly: Found {len(ids)} new PMIDs since last run")
    
    if limit:
        ids = ids[:limit]
        logger.info(f"Limited to {len(ids)} PMIDs")
    
    return ids


def process_papers(ids: List[str], mode: str) -> List[Dict]:
    """
    Process PMIDs through fetch → parse → score
    
    Args:
        ids: List of PMIDs
        mode: 'bootstrap' or 'monthly'
        
    Returns:
        List of parsed and scored papers
    """
    all_docs = []
    total_processed = 0
    
    logger.info(f"Processing {len(ids)} PMIDs in batches of 50...")
    
    for i in range(0, len(ids), 50):
        pid_batch = ids[i:i+50]
        
        try:
            xml = pubmed_efetch_xml(pid_batch)
            
            # Handle case where PubMed API returns string instead of XML
            if isinstance(xml, str):
                logger.warning(f"PubMed API returned string instead of XML for batch {i//50 + 1}, skipping...")
                continue
                
            arts = xml.get("PubmedArticleSet", {}).get("PubmedArticle", [])
            if isinstance(arts, dict):
                arts = [arts]

            for rec in arts:
                d = parse_pubmed_article(rec, None)  # No dynamic weights initially
                if d is None:
                    continue  # Skip irrelevant studies
                if not d["title"] and not d["content"]:
                    continue
                
                all_docs.append(d)
                total_processed += 1
                
                if total_processed % 100 == 0:
                    logger.info(f"Processed {total_processed} papers...")
        
        except Exception as e:
            logger.error(f"Error processing batch {i//50 + 1}: {e}")
            continue
    
    logger.info(f"Successfully processed {len(all_docs)} papers from {len(ids)} PMIDs")
    return all_docs


def apply_quality_filter(docs: List[Dict], mode: str) -> List[Dict]:
    """
    Apply quality floor filter
    
    Args:
        docs: List of papers
        mode: 'bootstrap' or 'monthly'
        
    Returns:
        Filtered list of papers
    """
    if mode == "bootstrap":
        quality_floor = QUALITY_FLOOR_BOOTSTRAP
    else:
        quality_floor = QUALITY_FLOOR_MONTHLY
    
    logger.info(f"Applying quality filter (floor: {quality_floor})...")
    
    filtered_docs = [d for d in docs if d.get("reliability_score", 0) >= quality_floor]
    
    logger.info(f"Quality filter: {len(docs)} -> {len(filtered_docs)} papers "
               f"(removed {len(docs) - len(filtered_docs)} low-quality)")
    
    return filtered_docs


def apply_diversity_selection(docs: List[Dict], target_count: int) -> List[Dict]:
    """
    Apply diversity-based selection
    
    Args:
        docs: List of papers
        target_count: Target number of papers to select
        
    Returns:
        Selected papers
    """
    logger.info(f"Applying diversity selection to {len(docs)} papers (target: {target_count})...")
    
    # Calculate combination weights
    combinations = analyze_combination_distribution(docs)
    combination_weights = calculate_combination_weights(combinations, len(docs))
    
    # Add combination scores to all papers
    for doc in docs:
        combination_score = calculate_combination_score(doc, combination_weights)
        doc["combination_score"] = combination_score
        doc["enhanced_score"] = doc.get("reliability_score", 0) + combination_score
    
    # Always run iterative diversity filtering if we have more papers than target
    if len(docs) > target_count:
        logger.info(f"Running iterative diversity filtering ({len(docs):,} papers → {target_count:,} papers)")
        selected_docs = iterative_diversity_filtering(
            papers=docs,
            target_count=target_count,
            elimination_per_round=5000  # Larger elimination rounds for 50K target
        )
    else:
        logger.info(f"Using simple top-K selection ({len(docs):,} papers ≤ {target_count:,} target)")
        # Sort by enhanced score and take top papers
        docs.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
        selected_docs = docs[:target_count]
    
    logger.info(f"Diversity selection complete: {len(selected_docs)} papers selected")
    return selected_docs


def main():
    """Main pipeline entry point"""
    parser = argparse.ArgumentParser(description="Get Papers Pipeline")
    parser.add_argument("--mode", choices=["bootstrap", "monthly"], default="bootstrap",
                       help="Run mode: bootstrap (comprehensive) or monthly (incremental)")
    parser.add_argument("--limit", type=int, help="Limit number of PMIDs to process")
    parser.add_argument("--target", type=int, default=INGEST_LIMIT,
                       help=f"Target number of papers to select (default: {INGEST_LIMIT})")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    logger.info("=" * 60)
    logger.info("GET PAPERS PIPELINE STARTING")
    logger.info("=" * 60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Target papers: {args.target}")
    if args.limit:
        logger.info(f"PMID limit: {args.limit}")
    logger.info(f"Quality floor - Bootstrap: {QUALITY_FLOOR_BOOTSTRAP}, Monthly: {QUALITY_FLOOR_MONTHLY}")
    logger.info(f"Diversity threshold: {DIVERSITY_ROUNDS_THRESHOLD}")
    
    start_time = time.time()
    
    try:
        # Step 1: Fetch PMIDs
        logger.info("\n" + "=" * 40)
        logger.info("STEP 1: FETCHING PMIDs")
        logger.info("=" * 40)
        
        ids = fetch_papers(args.mode, args.limit)
        if not ids:
            logger.warning("No PMIDs found. Exiting.")
            return
        
        # Step 2: Process papers
        logger.info("\n" + "=" * 40)
        logger.info("STEP 2: PROCESSING PAPERS")
        logger.info("=" * 40)
        
        all_docs = process_papers(ids, args.mode)
        if not all_docs:
            logger.warning("No papers processed. Exiting.")
            return
        
        # Step 3: Apply quality filter
        logger.info("\n" + "=" * 40)
        logger.info("STEP 3: APPLYING QUALITY FILTER")
        logger.info("=" * 40)
        
        quality_filtered_docs = apply_quality_filter(all_docs, args.mode)
        if not quality_filtered_docs:
            logger.warning("No papers passed quality filter. Exiting.")
            return
        
        # Step 4: Apply diversity selection
        logger.info("\n" + "=" * 40)
        logger.info("STEP 4: APPLYING DIVERSITY SELECTION")
        logger.info("=" * 40)
        
        selected_docs = apply_diversity_selection(quality_filtered_docs, args.target)
        if not selected_docs:
            logger.warning("No papers selected. Exiting.")
            return
        
        # Step 5: Save results
        logger.info("\n" + "=" * 40)
        logger.info("STEP 5: SAVING RESULTS")
        logger.info("=" * 40)
        
        # Save papers
        papers_file = save_selected_papers(selected_docs)
        
        # Create and save metadata
        run_info = {
            "mode": args.mode,
            "target_papers": args.target,
            "pmid_limit": args.limit,
            "quality_floor_bootstrap": QUALITY_FLOOR_BOOTSTRAP,
            "quality_floor_monthly": QUALITY_FLOOR_MONTHLY,
            "diversity_threshold": DIVERSITY_ROUNDS_THRESHOLD,
            "index_version": INDEX_VERSION
        }
        
        metadata = create_metadata_summary(selected_docs, run_info)
        metadata_file = save_run_metadata(metadata)
        
        # Update watermark for monthly mode
        if args.mode == "monthly":
            update_watermark()
        
        # Final summary
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info("\n" + "=" * 60)
        logger.info("GET PAPERS PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"PMIDs processed: {len(ids)}")
        logger.info(f"Papers parsed: {len(all_docs)}")
        logger.info(f"Papers after quality filter: {len(quality_filtered_docs)}")
        logger.info(f"Final papers selected: {len(selected_docs)}")
        logger.info(f"Papers file: {papers_file}")
        logger.info(f"Metadata file: {metadata_file}")
        
        # Show final distribution
        supplement_counts = {}
        for doc in selected_docs:
            supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
            for supp in supplements:
                supp = supp.strip()
                if supp:
                    supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        logger.info(f"Top supplements: {dict(sorted(supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10])}")
        
        # Show quality distribution
        quality_dist = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
        for doc in selected_docs:
            quality = doc.get("reliability_score", 0)
            if quality >= 4.0:
                quality_dist["4.0+"] += 1
            elif quality >= 3.0:
                quality_dist["3.0-3.9"] += 1
            elif quality >= 2.0:
                quality_dist["2.0-2.9"] += 1
            else:
                quality_dist["<2.0"] += 1
        
        logger.info(f"Quality distribution: {quality_dist}")
        
        # Show top enhanced scores
        top_scores = [d.get("enhanced_score", 0) for d in selected_docs[:5]]
        logger.info(f"Top enhanced scores: {top_scores}")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise


if __name__ == "__main__":
    main()
