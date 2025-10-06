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
from evidentfit_shared.utils import PROJECT_ROOT
# Add the parent directory to the path so we can import from get_papers
sys.path.insert(0, str(Path(__file__).parent.parent))

from get_papers.pubmed_client import multi_supplement_search, pubmed_efetch_xml, pubmed_esearch, PM_SEARCH_QUERY
from get_papers.parsing import parse_pubmed_article
from get_papers.diversity import (
    analyze_combination_distribution, 
    calculate_combination_weights, 
    calculate_combination_score,
    iterative_diversity_filtering,  # kept for existing callers
    iterative_diversity_filtering_with_protection,
    compute_minimum_quota_ids,
    compute_enhanced_quota_ids,
    should_run_iterative_diversity
)
from get_papers.storage import (
    create_run_dir,
    prune_old_runs,
    save_selected_papers,
    save_run_metadata,
    save_protected_quota_report,
    update_latest_pointer,
    create_metadata_summary,
    RUNS_BASE_DIR,
)
from get_papers.fulltext_fetcher import fetch_fulltexts_for_jsonl

logger = logging.getLogger(__name__)

# Environment variables with defaults
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")
# Default target lowered to 30k per our new baseline
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT", "30000"))
MAX_TOTAL_PAPERS = int(os.getenv("MAX_TOTAL_PAPERS", "500000"))
# Not strictly used for control flow, but keep consistent with 30k
DIVERSITY_ROUNDS_THRESHOLD = int(os.getenv("DIVERSITY_ROUNDS_THRESHOLD", "30000"))
QUALITY_FLOOR_BOOTSTRAP = float(os.getenv("QUALITY_FLOOR_BOOTSTRAP", "2.0"))
QUALITY_FLOOR_MONTHLY = float(os.getenv("QUALITY_FLOOR_MONTHLY", "2.0"))
WATERMARK_KEY = os.getenv("WATERMARK_KEY", "meta:last_ingest")
MIN_PER_SUPPLEMENT = int(os.getenv("MIN_PER_SUPPLEMENT", "3"))  # Legacy: simple quota (kept for compatibility)
INCLUDE_LOW_QUALITY_IN_MIN = os.getenv("INCLUDE_LOW_QUALITY_IN_MIN", "true").lower() == "true"
MIN_QUOTA_RARE_ONLY = os.getenv("MIN_QUOTA_RARE_ONLY", "false").lower() == "true"
RARE_THRESHOLD = int(os.getenv("RARE_THRESHOLD", "5"))
EXCLUDED_SUPPS_FOR_MIN = {s.strip() for s in os.getenv("EXCLUDED_SUPPS_FOR_MIN", "nitric-oxide").split(",") if s.strip()}

# Enhanced quota system (preferred)
USE_ENHANCED_QUOTAS = os.getenv("USE_ENHANCED_QUOTAS", "true").lower() == "true"
MIN_OVERALL_PER_SUPPLEMENT = int(os.getenv("MIN_OVERALL_PER_SUPPLEMENT", "10"))
MIN_PER_SUPPLEMENT_GOAL = int(os.getenv("MIN_PER_SUPPLEMENT_GOAL", "2"))
PREFER_FULLTEXT_IN_QUOTAS = os.getenv("PREFER_FULLTEXT_IN_QUOTAS", "true").lower() == "true"

# Diversity tiebreaking
DIVERSITY_TIEBREAK_THRESHOLD = float(os.getenv("DIVERSITY_TIEBREAK_THRESHOLD", "0.8"))
PREFER_FULLTEXT_IN_DIVERSITY = os.getenv("PREFER_FULLTEXT_IN_DIVERSITY", "true").lower() == "true"


def setup_logging() -> logging.Logger:
    """Setup logging for the pipeline"""
    log_level = os.getenv("LOG_LEVEL", "info").upper()
    log_level = getattr(logging, log_level, logging.INFO)
    
    # Create logs directory if it doesn't exist
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"get_papers_{timestamp}.log"
    
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
    
    Returns mindate 1 day before last ingest to catch papers added late on the last day.
    
    Returns:
        Mindate string in YYYY/MM/DD format or None
    """
    watermark_file = (PROJECT_ROOT / "data" / "ingest" / "watermark.json")
    if watermark_file.exists():
        try:
            import json
            with open(watermark_file, 'r', encoding='utf-8-sig') as f:
                watermark_data = json.load(f)
            last_ingest_iso = watermark_data.get("last_ingest_iso")
            if last_ingest_iso:
                dt = datetime.datetime.fromisoformat(last_ingest_iso.replace("Z", "+00:00"))
                # Subtract 1 day to catch papers added late on the last run day
                dt_minus_1 = dt - datetime.timedelta(days=1)
                return dt_minus_1.strftime("%Y/%m/%d")
        except Exception as e:
            logger.warning(f"Could not read watermark: {e}")
    
    return None


def update_watermark() -> None:
    """
    Update watermark with current timestamp for monthly mode.
    Stored in data/ingest/watermark.json (local file, not Azure Search).
    """
    watermark_file = (PROJECT_ROOT / "data" / "ingest" / "watermark.json")
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


def fetch_papers(mode: str) -> List[str]:
    """
    Fetch PMIDs based on mode
    
    Args:
        mode: 'bootstrap' or 'monthly'
        
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
    
    # De-duplicate PMIDs early
    before = len(ids)
    ids = sorted(set(ids))
    after = len(ids)
    logger.info(f"De-duplicated PMIDs: {before} -> {after}")
    
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
    seen_pmids = set()
    
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
                
                # Prevent duplicate docs across chunk boundaries
                pmid = d.get("pmid")
                if not pmid or pmid in seen_pmids:
                    continue
                seen_pmids.add(pmid)
                
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


def apply_diversity_selection(docs: List[Dict], target_count: int, protected_ids: Optional[set] = None) -> List[Dict]:
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
    
    # Use threshold for diversity selection
    total_docs = len(docs)
    threshold = DIVERSITY_ROUNDS_THRESHOLD
    run_div = should_run_iterative_diversity(total_docs, threshold)
    
    if run_div:
        logger.info(f"Iterative diversity ON (total={total_docs:,} > threshold={threshold:,}); selecting → {target_count:,}")
        selected_docs = iterative_diversity_filtering_with_protection(
            papers=docs,
            target_count=target_count,
            elimination_per_round=5000,  # Larger elimination rounds for 50K target
            protected_ids=protected_ids or set(),
            tiebreak_threshold=DIVERSITY_TIEBREAK_THRESHOLD,
            prefer_fulltext=PREFER_FULLTEXT_IN_DIVERSITY,
        )
    else:
        logger.info(f"Iterative diversity OFF (total={total_docs:,} <= threshold={threshold:,}); using top-K by enhanced_score")
        # Sort by enhanced score and take top papers
        docs.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
        selected_docs = docs[:target_count]
    
    # Summary log after selection
    gated_count = sum(1 for doc in selected_docs if doc.get("combination_score", 0) == 0)
    normalized_count = sum(1 for doc in selected_docs if 0 < doc.get("combination_score", 0) < 1.0)
    logger.info(f"Diversity selection complete: {len(selected_docs)} papers selected")
    logger.info(f"Selection summary: {gated_count} gated (combo_score=0), {normalized_count} normalized (0<combo_score<1)")
    
    # Sanity checks
    goal_specific_count = sum(1 for doc in selected_docs if doc.get("primary_goal") not in (None, "", "general"))
    pct_goal_specific = round(100.0 * goal_specific_count / len(selected_docs), 2)
    
    # Top 10 supplements
    supplement_counts = {}
    for doc in selected_docs:
        supplements = (doc.get("supplements") or "").split(",")
        for supp in supplements:
            if supp.strip():
                supplement_counts[supp.strip()] = supplement_counts.get(supp.strip(), 0) + 1
    top_supplements = sorted(supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Study type distribution
    study_type_counts = {}
    for doc in selected_docs:
        study_type = doc.get("study_type", "other")
        study_type_counts[study_type] = study_type_counts.get(study_type, 0) + 1
    
    # Quality distribution
    quality_counts = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    for doc in selected_docs:
        quality = doc.get("reliability_score", 0)
        if quality >= 4.0:
            quality_counts["4.0+"] += 1
        elif quality >= 3.0:
            quality_counts["3.0-3.9"] += 1
        elif quality >= 2.0:
            quality_counts["2.0-2.9"] += 1
        else:
            quality_counts["<2.0"] += 1
    
    # Top supplement-goal combinations
    combo_counts = {}
    for doc in selected_docs[:100]:  # Sample first 100
        supplements = (doc.get("supplements") or "").split(",")
        goal = doc.get("primary_goal", "")
        for supp in supplements:
            if supp.strip() and goal:
                key = f"{supp.strip()}_{goal}"
                combo_counts[key] = combo_counts.get(key, 0) + 1
    top_combos = sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    logger.info(f"Sanity checks:")
    logger.info(f"  Goal-specific papers: {pct_goal_specific}% ({goal_specific_count}/{len(selected_docs)})")
    logger.info(f"  Top supplements: {[f'{s}({c})' for s, c in top_supplements[:5]]}")
    logger.info(f"  Study types: {dict(sorted(study_type_counts.items(), key=lambda x: x[1], reverse=True))}")
    logger.info(f"  Quality distribution: {quality_counts}")
    logger.info(f"  Top combos: {[f'{c}({n})' for c, n in top_combos[:5]]}")
    
    return selected_docs


def print_dry_report(selected_docs: List[Dict]) -> None:
    """Print dry-run report with study categories and top supplements"""
    print("\n" + "=" * 50)
    print("DRY-RUN REPORT")
    print("=" * 50)
    
    # Count by study category
    category_counts = {}
    for doc in selected_docs:
        category = doc.get("study_category", "other")
        category_counts[category] = category_counts.get(category, 0) + 1
    
    print("\nStudy Categories:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    
    # Top supplements
    supplement_counts = {}
    for doc in selected_docs:
        supplements = (doc.get("supplements") or "").split(",")
        for supp in supplements:
            if supp.strip():
                supplement_counts[supp.strip()] = supplement_counts.get(supp.strip(), 0) + 1
    
    print("\nTop 10 Supplements:")
    for supp, count in sorted(supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {supp}: {count}")
    
    # Combination score stats
    gated_count = sum(1 for doc in selected_docs if doc.get("combination_score", 0) == 0)
    print(f"\nCombination Score Stats:")
    print(f"  Gated (combo_score=0): {gated_count}")
    print(f"  Total papers: {len(selected_docs)}")


def main():
    """Main pipeline entry point"""
    parser = argparse.ArgumentParser(description="Get Papers Pipeline")
    parser.add_argument("--mode", choices=["bootstrap", "monthly"], default="bootstrap",
                       help="Run mode: bootstrap (comprehensive) or monthly (incremental)")
    parser.add_argument("--target", type=int, default=INGEST_LIMIT,
                       help=f"Target number of papers to select (default: {INGEST_LIMIT})")
    parser.add_argument("--dry_report", type=int, help="Print dry-run report with N papers (no processing)")
    # Fulltext fetching is now default ON (PMC only)
    parser.add_argument("--fetch-fulltext", dest="fetch_fulltext", action="store_true", help="Fetch PMC full texts for selected papers (default)")
    parser.add_argument("--no-fetch-fulltext", dest="fetch_fulltext", action="store_false", help="Skip full text fetching")
    parser.set_defaults(fetch_fulltext=True)
    parser.add_argument("--fulltext-limit", type=int, default=None, help="Optional cap when fetching full texts")
    parser.add_argument("--fulltext-concurrency", type=int, default=8, help="Max concurrent PMC requests")
    parser.add_argument("--fulltext-store", type=str, default=str((PROJECT_ROOT / "data" / "fulltext_store").as_posix()),
                       help="Centralized full-text store directory")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    logger.info("=" * 60)
    logger.info("GET PAPERS PIPELINE STARTING")
    logger.info("=" * 60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Target papers: {args.target}")
    logger.info(f"Quality floor - Bootstrap: {QUALITY_FLOOR_BOOTSTRAP}, Monthly: {QUALITY_FLOOR_MONTHLY}")
    logger.info(f"Diversity threshold: {DIVERSITY_ROUNDS_THRESHOLD}")
    logger.info(f"Fulltext fetch enabled: {args.fetch_fulltext} (PMC only)")
    
    start_time = time.time()
    
    try:
        # Step 1: Fetch PMIDs
        logger.info("\n" + "=" * 40)
        logger.info("STEP 1: FETCHING PMIDs")
        logger.info("=" * 40)
        
        ids = fetch_papers(args.mode)
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
        
        # Step 3: Apply quality filter (but we'll protect a per-supplement minimum set)
        logger.info("\n" + "=" * 40)
        logger.info("STEP 3: APPLYING QUALITY FILTER")
        logger.info("=" * 40)
        
        quality_filtered_docs = apply_quality_filter(all_docs, args.mode)

        # Build protected (minimum quota) set from ALL docs (pre-quality filter)
        if USE_ENHANCED_QUOTAS:
            logger.info(f"Using enhanced quota system: {MIN_OVERALL_PER_SUPPLEMENT} overall + {MIN_PER_SUPPLEMENT_GOAL} per goal")
            protected_ids = compute_enhanced_quota_ids(
                all_docs=all_docs,
                min_overall=MIN_OVERALL_PER_SUPPLEMENT,
                min_per_goal=MIN_PER_SUPPLEMENT_GOAL,
                prefer_fulltext=PREFER_FULLTEXT_IN_QUOTAS,
                quality_floor=QUALITY_FLOOR_BOOTSTRAP if args.mode == "bootstrap" else QUALITY_FLOOR_MONTHLY,
            )
        else:
            logger.info(f"Using legacy quota system: {MIN_PER_SUPPLEMENT} per supplement")
            protected_ids = compute_minimum_quota_ids(
                all_docs=all_docs,
                min_per_supp=MIN_PER_SUPPLEMENT,
                include_low_quality=INCLUDE_LOW_QUALITY_IN_MIN,
                rare_only=MIN_QUOTA_RARE_ONLY,
                rare_threshold=RARE_THRESHOLD,
                exclude_supps=EXCLUDED_SUPPS_FOR_MIN,
                quality_floor=QUALITY_FLOOR_BOOTSTRAP if args.mode == "bootstrap" else QUALITY_FLOOR_MONTHLY,
            )
        if protected_ids:
            # ensure protected docs survive the quality filter (union them back in)
            keep_ids = {d.get("id") for d in quality_filtered_docs}
            added = 0
            for d in all_docs:
                if d.get("id") in protected_ids and d.get("id") not in keep_ids:
                    quality_filtered_docs.append(d)
                    keep_ids.add(d.get("id"))
                    added += 1
            logger.info(f"Protected per-supplement minimum added back after quality filter: {added} docs")
        if not quality_filtered_docs:
            logger.warning("No papers passed quality filter. Exiting.")
            return
        
        # Step 4: Apply diversity selection
        logger.info("\n" + "=" * 40)
        logger.info("STEP 4: APPLYING DIVERSITY SELECTION")
        logger.info("=" * 40)
        
        selected_docs = apply_diversity_selection(quality_filtered_docs, args.target, protected_ids=protected_ids)
        if not selected_docs:
            logger.warning("No papers selected. Exiting.")
            return
        
        # Dry-run report if requested
        if args.dry_report:
            print_dry_report(selected_docs[:args.dry_report])
            return
        
        # Step 5: Save results
        logger.info("\n" + "=" * 40)
        logger.info("STEP 5: SAVING RESULTS")
        logger.info("=" * 40)

        # Create a timestamped run dir and save artifacts
        run_id, run_dir = create_run_dir()
        papers_file = save_selected_papers(selected_docs, run_dir)

        # ---- Build protected-quota report (how many reserved actually made it) ----
        from collections import Counter

        def _supp_list(doc):
            raw = (doc.get("supplements") or "").split(",")
            return [s.strip() for s in raw if s.strip()]

        # Map doc_id -> supplements using the full parsed pool (so we can attribute protected IDs)
        id_to_supps = {}
        for d in all_docs:
            if d.get("id"):
                id_to_supps[d["id"]] = _supp_list(d)

        # Totals reserved per supplement (in protected set), and how many of those survived to final
        reserved_per_supp = Counter()
        for pid in protected_ids:
            for s in id_to_supps.get(pid, []):
                reserved_per_supp[s] += 1

        kept_protected_ids = {d.get("id") for d in selected_docs if d.get("id") in protected_ids}
        kept_per_supp = Counter()
        for d in selected_docs:
            if d.get("id") in kept_protected_ids:
                for s in _supp_list(d):
                    kept_per_supp[s] += 1

        protected_report = {
            "protected_total_reserved": len(protected_ids),
            "protected_total_kept": len(kept_protected_ids),
            "per_supplement": {
                s: {
                    "reserved": reserved_per_supp.get(s, 0),
                    "kept": kept_per_supp.get(s, 0),
                    "kept_ratio": (float(kept_per_supp[s]) / reserved_per_supp[s]) if reserved_per_supp[s] else None,
                }
                for s in sorted(set(list(reserved_per_supp.keys()) + list(kept_per_supp.keys())))
            },
        }
        protected_report_path = save_protected_quota_report(protected_report, run_dir)

        # Log a brief summary
        logger.info(f"Protected quota - kept {protected_report['protected_total_kept']} of {protected_report['protected_total_reserved']} reserved IDs")
        # Show top 10 supplements by reserved count
        top_reserved = sorted(protected_report["per_supplement"].items(), key=lambda kv: kv[1]["reserved"], reverse=True)[:10]
        logger.info(f"Protected quota (top by reserved): { {k: v for k, v in top_reserved} }")

        # Create and save metadata (include stage counts so metadata.json shows pre-diversity numbers)
        run_info = {
            "mode": args.mode,
            "target_papers": args.target,
            "quality_floor_bootstrap": QUALITY_FLOOR_BOOTSTRAP,
            "quality_floor_monthly": QUALITY_FLOOR_MONTHLY,
            "diversity_threshold": DIVERSITY_ROUNDS_THRESHOLD,
            "index_version": INDEX_VERSION,
            "run_id": run_id,
            "run_dir": str(run_dir.as_posix()),
            "papers_path": str(papers_file.as_posix()),
            # Stage counts
            "pmids_found": len(ids),
            "papers_parsed": len(all_docs),
            "papers_after_quality": len(quality_filtered_docs),
            # Alias for clarity: "before diversity" == "after quality"
            "papers_before_diversity": len(quality_filtered_docs),
            "papers_selected_final": len(selected_docs),
            "diversity_applied": len(quality_filtered_docs) > args.target,
            "protected_total_reserved": protected_report["protected_total_reserved"],
            "protected_total_kept": protected_report["protected_total_kept"],
            "protected_quota_report_path": str(protected_report_path.as_posix()),
        }
        
        metadata = create_metadata_summary(selected_docs, run_info)
        metadata_file = save_run_metadata(metadata, run_dir)

        
        # Update watermark (for both bootstrap and monthly)
        # Bootstrap creates initial watermark; monthly updates it for next run
        update_watermark()
        
        # Step 6: Fetch PMC full texts — default ON
        fulltext_store_dir = Path(args.fulltext_store)
        fulltext_manifest_path = None
        if args.fetch_fulltext:
            logger.info("\n" + "=" * 40)
            logger.info("STEP 6: FETCHING FULL TEXTS (PMC when available)")
            logger.info("=" * 40)
            run_manifest_dir = run_dir  # write manifest into the run dir
            try:
                ft_manifest = fetch_fulltexts_for_jsonl(
                    papers_file,
                    fulltext_store_dir,
                    run_manifest_dir,
                    max_concurrency=args.fulltext_concurrency,
                    limit=args.fulltext_limit,
                    overwrite=False
                )
                fulltext_manifest_path = run_manifest_dir / "fulltext_manifest.json"
                logger.info(f"Full-text manifest: {ft_manifest}")
            except Exception as e:
                logger.error(f"Full-text fetch step failed: {e}")
        else:
            logger.info("Skipping full-text fetching (--no-fetch-fulltext)")
        
        # Update latest pointer + prune old runs
        latest_file = update_latest_pointer(
            run_id,
            run_dir,
            papers_file,
            metadata_file,
            fulltext_dir=None,  # we don't store fulltexts inside the run anymore
            fulltext_store_dir=fulltext_store_dir,
            fulltext_manifest=fulltext_manifest_path
        )
        prune_old_runs()
        
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
        if 'fulltext_manifest_path' in locals() and fulltext_manifest_path and fulltext_manifest_path.exists():
            logger.info(f"Fulltext manifest: {fulltext_manifest_path}")
        logger.info(f"Latest pointer: {RUNS_BASE_DIR / 'latest.json'}")
        
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
