#!/usr/bin/env python3
"""
EvidentFit Paper Processor - Simplified Single-Pass Pipeline

This module processes research papers using a simplified approach:
1. Collect section bundles from database with smart truncation
2. Single-pass LLM extraction with enhanced schema
3. Quality validation and database storage
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# Import shared utilities
try:
    from evidentfit_shared.utils import read_index_version
except ImportError:
    def read_index_version():
        return "v1-2025-01-15"  # fallback

# Local imports
from .collect import build_section_bundle
from .extract import extract_from_bundle
from .schema import normalize_data, create_dedupe_key, validate_optimized_schema
from .validation import validate_card, log_validation_results
from .db_writer import write_card_to_db
from .storage_manager import StorageManager
from .logging_config import setup_logging

import torch

# Set up database environment
os.environ['EVIDENTFIT_DB_DSN'] = 'postgresql://postgres:Winston8891**@localhost:5432/evidentfit'

LOG = logging.getLogger(__name__)


def resolve_selected_papers(papers_jsonl: str = None) -> Path:
    """Resolve the papers JSONL file path."""
    if papers_jsonl:
        return Path(papers_jsonl)
    
    # Default to latest pointer
    latest_path = Path("data/paper_processor/latest.json")
    if latest_path.exists():
        with open(latest_path, "r") as f:
            latest_data = json.load(f)
            return Path(latest_data.get("papers_jsonl", "data/index/canonical_papers.jsonl"))
    
    return Path("data/index/canonical_papers.jsonl")


def stream_jsonl(path: Path, limit: int = None):
    """Stream JSONL file with optional limit."""
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if limit and count >= limit:
                break
            if line.strip():
                try:
                    yield json.loads(line.strip())
                    count += 1
                except json.JSONDecodeError:
                    continue


def main():
    """Main processing function."""
    # Parse arguments
    ap = argparse.ArgumentParser(description="EvidentFit paper processor (simplified single-pass)")
    ap.add_argument("--papers-jsonl", type=str, help="Path to pm_papers.jsonl (optional; defaults to runs/latest.json pointer)")
    ap.add_argument("--max-papers", type=int, default=200, help="Max papers to process")
    ap.add_argument("--dry-run", action="store_true", help="Skip model loading and LLM processing for testing")
    ap.add_argument("--model", type=str, default=None, help="Model path")
    ap.add_argument("--quant", type=str, choices=["none", "4bit", "8bit", "8bit-offload"], default="4bit", 
                   help="Quantization level: none (no quantization), 4bit (4-bit quantization), 8bit (8-bit GPU-only), 8bit-offload (8-bit with CPU offload)")
    ap.add_argument("--temperature", type=float, default=0.0, help="0.0 for deterministic output; >0 enables sampling")
    ap.add_argument("--seed", type=int, default=None, help="Global RNG seed for reproducibility")
    ap.add_argument("--master-summaries", type=str, default=None, 
                   help="Path to master summaries file (default: data/paper_processor/master/summaries_master.jsonl)")
    ap.add_argument("--pointer-interval", type=int, default=20, 
                   help="How often (in input papers) to refresh data/paper_processor/latest.json")
    ap.add_argument("--log-interval", type=int, default=100, 
                   help="How often (in successful outputs) to log progress")
    ap.add_argument("--slow-threshold-sec", type=float, default=60.0, 
                   help="Threshold in seconds to consider a paper slow")
    ap.add_argument("--preflight-only", action="store_true", 
                   help="Run preflight validation only, don't process papers")
    args = ap.parse_args()
    
    # Setup
    run_id = f"paper_processor_{int(time.time())}"
    setup_logging()
    LOG.info("=" * 80)
    LOG.info("PAPER PROCESSOR START (SIMPLIFIED SINGLE-PASS)")
    LOG.info("=" * 80)
    LOG.info(f"Run ID: {run_id}")
    
    # Resolve papers file
    papers_jsonl = resolve_selected_papers(args.papers_jsonl)
    LOG.info(f"Selected papers: {papers_jsonl}")
    
    # Set canonical path for collect bundles
    canonical_path = Path(papers_jsonl)
    
    # Log database connection
    try:
        dsn = os.environ.get('EVIDENTFIT_DB_DSN', 'Not set')
        LOG.info(f"Database DSN: {dsn.replace('Winston8891**', '***')}")
    except Exception as e:
        LOG.warning(f"Could not get database DSN: {e}")
    
    # Load meta_map once to avoid reloading for every paper
    LOG.info("Loading paper metadata...")
    from .collect import _load_meta_map
    meta_map = _load_meta_map(canonical_path)
    LOG.info(f"Loaded metadata for {len(meta_map)} papers")
    
    # Preflight validation
    if args.preflight_only:
        LOG.info("Running preflight-only validation...")
        total = 0
        db_full = 0
        db_abs = 0
        db_missing = 0
        db_no_text = 0
        
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            total += 1
            pmid_val = p.get("pmid")
            if not pmid_val:
                db_missing += 1
                continue
            
            try:
                db_pmid = str(pmid_val)
                if not db_pmid.startswith('pmid_'):
                    db_pmid = f"pmid_{db_pmid}"
                
                bundle = build_section_bundle(db_pmid, canonical_path, meta_map=meta_map)
                if not bundle or not bundle.sections:
                    db_missing += 1
                    continue
                
                has_fulltext = bundle.stats.get("has_fulltext", False)
                if has_fulltext:
                    db_full += 1
                else:
                    abstract_data = bundle.sections.get("abstract", {})
                    abstract_text = abstract_data.get("text", "").strip()
                    if abstract_text:
                        db_abs += 1
                    else:
                        db_no_text += 1
                        
            except Exception as e:
                LOG.warning(f"Preflight error for PMID {pmid_val}: {e}")
                db_missing += 1
                continue
                
        LOG.info(f"Preflight: total={total}, db_fulltext={db_full}, db_abstract={db_abs}, db_missing={db_missing}, db_no_text={db_no_text}")
        print(f"Preflight complete. total={total}, fulltext={db_full}, abstract={db_abs}, missing={db_missing}, no_text={db_no_text}")
        return
    
    # Determine LLM mode: cloud (GPT-4o-mini) or local (Mistral-7B)
    use_cloud = os.getenv("PAPER_PROCESSOR_USE_CLOUD", "1").lower() in ("1", "true", "yes")
    
    if use_cloud:
        # Use GPT-4o-mini via Azure AI Foundry
        LOG.info("Using GPT-4o-mini (Azure AI Foundry) for paper processing")
        
        if args.dry_run:
            LOG.info("DRY RUN MODE: Skipping client initialization")
            client = None
        else:
            from .foundry_client import GPT4oMiniClient
            client = GPT4oMiniClient()
            LOG.info("GPT-4o-mini client initialized")
    else:
        # Legacy: Use Mistral-7B local GPU
        LOG.info("Using Mistral-7B (local GPU) for paper processing")
        
        # Resolve model path
        if not args.model:
            candidates = [
                Path("E:/models/Mistral-7B-Instruct-v0.3"),  # Windows
                Path("E:\\models\\Mistral-7B-Instruct-v0.3"),  # Windows
                Path("/mnt/e/models/Mistral-7B-Instruct-v0.3"),  # Ubuntu WSL
                Path("/home/melunis/models/Mistral-7B-Instruct-v0.3"),  # Ubuntu
                Path("models/Mistral-7B-Instruct-v0.3")
            ]
            
            for candidate in candidates:
                if candidate.exists():
                    args.model = str(candidate)
                    break
            
            if not args.model:
                args.model = "mistralai/Mistral-7B-Instruct-v0.3"  # HuggingFace fallback
        
        LOG.info(f"Using model: {args.model}")
        
        # Set quantization environment variables BEFORE importing MistralClient
        if args.quant == "8bit":
            os.environ["EVIDENTFIT_QUANT_8BIT"] = "1"
            os.environ["EVIDENTFIT_QUANT_4BIT"] = "0"
        elif args.quant == "8bit-offload":
            os.environ["EVIDENTFIT_QUANT_8BIT"] = "offload"
            os.environ["EVIDENTFIT_QUANT_4BIT"] = "0"
        elif args.quant == "4bit":
            os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"
            os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
        else:  # none
            os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"
            os.environ["EVIDENTFIT_QUANT_4BIT"] = "0"
        
        # Debug: Log the environment variables
        LOG.info(f"Quantization settings: 8bit={os.environ.get('EVIDENTFIT_QUANT_8BIT')}, 4bit={os.environ.get('EVIDENTFIT_QUANT_4BIT')}")
        
        # Initialize client
        if args.dry_run:
            LOG.info("DRY RUN MODE: Skipping model loading")
            client = None
        else:
            LOG.info("Loading model... (this may take 20-30 seconds)")
            from .mistral_client import MistralClient
            
            client = MistralClient(model_name=args.model)
    
    # Initialize storage
    storage = StorageManager()
    storage.initialize()
    
    # Resolve master path and setup
    master_path = Path(args.master_summaries) if args.master_summaries else storage.paths.summaries_dir / "summaries_master.jsonl"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing dedupe keys
    seen_keys = set()
    if master_path.exists():
        with open(master_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line.strip())
                        dkey = data.get("dedupe_key")
                        if dkey:
                            seen_keys.add(dkey)
                    except json.JSONDecodeError:
                        continue
    
    master_size_before = len(seen_keys)
    LOG.info(f"Master size before: {master_size_before:,} papers")
    
    # Initialize storage writer
    storage.open_summaries_writer(master_path)
    
    # Initialize counters and metrics
    papers_in = 0
    papers_out = 0
    skipped_empty = 0
    skipped_dedup = 0
    skipped_no_text = 0
    store_fulltext_used = 0
    store_abstract_used = 0
    store_missing = 0
    store_no_text = 0
    failed_papers = []
    slow_papers = []
    per_paper_latency = []
    year_values = []
    study_type_counts = {}
    supplement_counts = {}
    gpu_memory_usage = []
    
    # Quality metrics
    quality_metrics = {
        "total": 0,
        "high_quality": 0,
        "low_quality": 0,
        "quality_scores": []
    }
    
    start = time.time()
    
    try:
        # Main processing loop
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            papers_in += 1
            t0 = time.time()
            
            pmid_val = p.get("pmid")
            if not pmid_val:
                store_missing += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning("No PMID found for paper")
                continue
            
            try:
                # Convert PMID to database format
                db_pmid = str(pmid_val)
                if not db_pmid.startswith('pmid_'):
                    db_pmid = f"pmid_{db_pmid}"
                
                # Get section bundle with smart truncation
                bundle = build_section_bundle(db_pmid, canonical_path, meta_map=meta_map)
                if not bundle or not bundle.sections:
                    store_missing += 1
                    skipped_empty += 1
                    skipped_no_text += 1
                    LOG.warning(f"No bundle found for PMID {pmid_val}")
                    continue
                
                # Check if we have any content
                has_content = any(section.get("text", "").strip() for section in bundle.sections.values())
                if not has_content:
                    store_no_text += 1
                    skipped_empty += 1
                    skipped_no_text += 1
                    LOG.warning(f"No content found for PMID {pmid_val}")
                    continue
                
                # Determine content source
                has_fulltext = bundle.stats.get("has_fulltext", False)
                if has_fulltext:
                    store_fulltext_used += 1
                else:
                    store_abstract_used += 1
                
            except Exception as e:
                store_missing += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning(f"Error collecting bundle for PMID {pmid_val}: {e}")
                continue
            
            # Check for duplicates
            dkey = create_dedupe_key(p)
            if dkey in seen_keys:
                skipped_dedup += 1
                continue
            seen_keys.add(dkey)
            
            # Single-pass extraction
            try:
                # Add metadata to bundle
                bundle.meta.update({
                    "pmid": p.get("pmid"),
                    "doi": p.get("doi"),
                    "title": p.get("title"),
                    "journal": p.get("journal"),
                    "year": p.get("year"),
                    "supplements": p.get("supplements", []),
                    "primary_goal": p.get("primary_goal", "general")
                })
                
                # Extract using single-pass LLM
                if args.dry_run:
                    extracted = {
                        "population_size": 100,
                        "population_characteristics": {"age_mean": 45.0, "sex_distribution": "50% male, 50% female", "training_status": "untrained"},
                        "intervention_details": {"dose_g_per_day": 5.0, "dose_mg_per_kg": 71.4, "duration_weeks": 8, "loading_phase": False, "supplement_forms": "creatine monohydrate"},
                        "effect_sizes": [{"measure": "strength", "value": 0.15, "significance": "p<0.05"}],
                        "safety_details": {"adverse_events": "none reported", "contraindications": "none", "safety_grade": "A"},
                        "key_findings": ["Creatine supplementation increased strength by 15%", "No adverse events were observed"]
                    }
                else:
                    extracted = extract_from_bundle(bundle, client)
                
                if not extracted:
                    LOG.warning(f"Extraction failed for PMID {pmid_val}")
                    failed_papers.append({
                        "pmid": p.get("pmid"),
                        "doi": p.get("doi"),
                        "title": p.get("title", "")[:100],
                        "reason": "extraction_failed"
                    })
                    continue
                
                # Normalize and validate
                normalized = normalize_data(extracted)
                if not validate_optimized_schema(normalized):
                    LOG.warning(f"Schema validation failed for PMID {pmid_val}")
                    failed_papers.append({
                        "pmid": p.get("pmid"),
                        "doi": p.get("doi"),
                        "title": p.get("title", "")[:100],
                        "reason": "schema_validation_failed"
                    })
                    continue
                
                # Quality validation
                is_valid, quality_score, missing = validate_card(normalized)
                normalized["extraction_confidence"] = quality_score
                
                # Update quality metrics
                quality_metrics["total"] += 1
                quality_metrics["quality_scores"].append(quality_score)
                if quality_score >= 0.80:
                    quality_metrics["high_quality"] += 1
                elif quality_score < 0.60:
                    quality_metrics["low_quality"] += 1
                    LOG.warning(f"Low quality ({quality_score:.2f}) for PMID {p.get('pmid')}: missing {missing}")
                
                # Add metadata
                normalized.update({
                    "id": f"pmid_{pmid_val}",
                    "pmid": pmid_val,
                    "doi": p.get("doi"),
                    "title": p.get("title"),
                    "journal": p.get("journal"),
                    "year": p.get("year"),
                    "supplements": p.get("supplements", []),
                    "study_type": p.get("study_type", "unknown"),
                    "dedupe_key": dkey,
                    "input_source": "fulltext" if has_fulltext else "abstract",
                    "input_chars": sum(section.get("char_len", 0) for section in bundle.sections.values())
                })
                
                # Add quality score from paper metadata
                try:
                    qsource = None
                    for key in ("relevance_score", "reliability_score", "study_design_score"):
                        if p.get(key) is not None:
                            qsource = float(p.get(key))
                            break
                    if qsource is not None:
                        normalized["quality_score"] = qsource
                    else:
                        normalized.pop("quality_score", None)
                except Exception:
                    normalized.pop("quality_score", None)
                
                # Remove evidence_grade
                normalized.pop("evidence_grade", None)
                
                # Write to storage
                storage.write_summary_line_monthly(normalized)
                
                # Write to database
                try:
                    write_card_to_db(normalized)
                except Exception as e:
                    LOG.warning(f"Database write error for PMID {p.get('pmid')}: {e}")
                
                papers_out += 1
                
                # Clear memory
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Update stats
                paper_elapsed = time.time() - t0
                per_paper_latency.append(paper_elapsed)
                
                if paper_elapsed > args.slow_threshold_sec:
                    slow_papers.append({
                        "pmid": p.get("pmid"),
                        "elapsed": paper_elapsed
                    })
                
                # Update aggregates
                y = normalized.get("year")
                if isinstance(y, int):
                    year_values.append(y)
                
                st = normalized.get("study_type", "unknown")
                study_type_counts[st] = study_type_counts.get(st, 0) + 1
                
                for s in (normalized.get("supplements") or []):
                    if s:
                        supplement_counts[s] = supplement_counts.get(s, 0) + 1
                
                # Capture GPU memory usage periodically
                if torch.cuda.is_available() and idx % 10 == 0:
                    try:
                        gpu_memory = torch.cuda.max_memory_allocated() / (1024**3)
                        gpu_memory_usage.append(gpu_memory)
                    except Exception:
                        pass
                
                # Log progress
                if idx % args.log_interval == 0:
                    LOG.info(f"Processed {idx}/{args.max_papers} papers, {papers_out} successful")
                
                # Update pointer
                if idx % args.pointer_interval == 0:
                    tmp_path, final_path = storage.get_current_writer_paths()
                    if tmp_path or final_path:
                        storage.update_latest_pointer((tmp_path or final_path))
                
            except Exception as e:
                LOG.warning(f"Processing failed for PMID {pmid_val}: {e}")
                failed_papers.append({
                    "pmid": p.get("pmid"),
                    "doi": p.get("doi"),
                    "title": p.get("title", "")[:100],
                    "reason": f"processing_error: {str(e)[:100]}"
                })
                continue
        
        # Close storage writer
        final_summaries_path = storage.close_summaries_writer()
        
        # Calculate final stats
        master_size_after = 0
        if master_path.exists():
            with open(master_path, "r", encoding="utf-8") as f:
                master_size_after = sum(1 for line in f if line.strip())
        
        LOG.info(f"Master size after: {master_size_after:,} papers (+{master_size_after - master_size_before:,})")
        
        # Rebuild master index
        LOG.info("Rebuilding master index...")
        index = storage.build_master_index(master_path)
        index_path = storage.save_master_index(index, master_path)
        LOG.info(f"Master index saved: {index_path} ({len(index):,} entries)")
        
        # Master validation
        LOG.info("Validating master...")
        valid, errors = storage.validate_master(master_path, index_path)
        if not valid:
            LOG.error(f"Master validation failed: {errors}")
        else:
            LOG.info("Master validation passed")
        
        elapsed = time.time() - start
        
        # Compile final stats
        stats = {
            "run_id": run_id,
            "mode": "simplified_single_pass",
            "papers_in": papers_in,
            "papers_out": papers_out,
            "skipped_empty": skipped_empty,
            "skipped_dedup": skipped_dedup,
            "coverage_ratio": (papers_out / papers_in) if papers_in else None,
            
            # Store usage
            "store_fulltext_used": store_fulltext_used,
            "store_abstract_used": store_abstract_used,
            "store_fulltext_ratio": (store_fulltext_used / papers_out) if papers_out > 0 else 0.0,
            
            # Error recovery
            "failed_papers": failed_papers,
            "failed_count": len(failed_papers),
            "failure_rate": (len(failed_papers) / papers_in) if papers_in > 0 else 0.0,
            
            # Performance monitoring
            "slow_papers": slow_papers,
            "slow_count": len(slow_papers),
            "slow_rate": (len(slow_papers) / papers_out) if papers_out > 0 else 0.0,
            
            # Skip breakdown
            "skipped_no_text": skipped_no_text,
            
            # Fulltext store diagnostics
            "store_missing": store_missing,
            "store_no_text": store_no_text,
            
            # Quality metrics
            "quality_metrics": quality_metrics,
            
            # Timing
            "elapsed_seconds": elapsed,
            "papers_per_minute": (papers_out / elapsed * 60) if elapsed > 0 else 0.0,
            "avg_paper_latency": (sum(per_paper_latency) / len(per_paper_latency)) if per_paper_latency else 0.0,
            
            # Year distribution
            "year_range": [min(year_values), max(year_values)] if year_values else None,
            "year_count": len(year_values),
            
            # Study type distribution
            "study_type_counts": dict(study_type_counts),
            
            # Supplement distribution
            "supplement_counts": dict(supplement_counts),
            
            # GPU memory usage
            "gpu_memory_usage": gpu_memory_usage,
            "max_gpu_memory": max(gpu_memory_usage) if gpu_memory_usage else 0.0,
            "avg_gpu_memory": (sum(gpu_memory_usage) / len(gpu_memory_usage)) if gpu_memory_usage else 0.0,
            
            # File paths
            "master_path": str(master_path),
            "index_path": str(index_path) if index_path else None,
            
            # Master size tracking
            "master_size_before": master_size_before,
            "master_size_after": master_size_after,
            "master_size_delta": master_size_after - master_size_before,
        }
        
        # Save stats
        stats_path = storage.paths.summaries_dir / f"run_stats_{run_id}.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        LOG.info(f"Stats saved: {stats_path}")
        
        # Print summary
        print("=" * 80)
        print(f"PAPER PROCESSOR COMPLETE")
        print(f"Run ID: {run_id}")
        print(f"Mode: {stats['mode']}")
        print(f"Papers: {papers_in} in, {papers_out} out ({stats['coverage_ratio']:.1%} coverage)")
        print(f"Store: {store_fulltext_used} fulltext, {store_abstract_used} abstract")
        if quality_metrics['total'] > 0:
            print(f"Quality: {quality_metrics['high_quality']}/{quality_metrics['total']} high quality ({quality_metrics['high_quality']/quality_metrics['total']*100:.1f}%)")
        if gpu_memory_usage:
            print(f"GPU Memory: max={max(gpu_memory_usage):.1f}GB, avg={sum(gpu_memory_usage)/len(gpu_memory_usage):.1f}GB")
        print(f"Time: {elapsed/3600:.2f} hours ({papers_out/elapsed*60:.1f} papers/min)")
        if per_paper_latency:
            print(f"Latency: min={min(per_paper_latency):.1f}s, "
                  f"median={sorted(per_paper_latency)[len(per_paper_latency)//2]:.1f}s, "
                  f"max={max(per_paper_latency):.1f}s")
        print(f"Output: {final_summaries_path}")
        print("=" * 80)
        
    except Exception as e:
        LOG.exception(f"Processor error: {e}")
        # Attempt to close writer and save partial stats
        try:
            try:
                final_summaries_path = storage.close_summaries_writer()
            except Exception:
                tmp_path, final_path = storage.get_current_writer_paths()
                final_summaries_path = (final_path or tmp_path or storage.paths.summaries_dir)
            elapsed = time.time() - start
            partial_stats = {
                "run_id": run_id,
                "mode": "simplified_single_pass",
                "papers_in": papers_in,
                "papers_out": papers_out,
                "elapsed_seconds": elapsed,
                "error": str(e),
                "partial": True
            }
            stats_path = storage.paths.summaries_dir / f"run_stats_{run_id}_partial.json"
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump(partial_stats, f, indent=2, ensure_ascii=False)
            LOG.info(f"Partial stats saved: {stats_path}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()