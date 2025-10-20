#!/usr/bin/env python3
"""
Paper processing pipeline (streaming + resume + VRAM-friendly).

- Resolves selected papers (pm_papers.jsonl)
- Streams papers from disk (low RAM)
- Chunks long content safely within model context
- Dedupes within the run (cheap guard)
- Streams summaries to JSONL (low RAM)
- Can resume a partial run using --resume-summaries
- Saves processing stats with coverage + timing
"""

import argparse
import os
import json
import time
import signal
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Iterator, List
from collections import Counter

from evidentfit_shared.utils import PROJECT_ROOT
from .logging_config import setup_logging
from .storage_manager import StorageManager
from .mistral_client import MistralClient
from .schema import (
    normalize_data,
    create_dedupe_key,
    validate_optimized_schema,
)
from .collect import build_section_bundle

import torch

# Set up database environment for collect bundles
os.environ['EVIDENTFIT_DB_DSN'] = 'postgresql://postgres:Winston8891**@localhost:5432/evidentfit'

LOG = logging.getLogger(__name__)

# -------------------------
# Helpers
# -------------------------

def stream_jsonl(path: Path, limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
    """Yield one JSON object per line up to limit (if provided)."""
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            yield obj
            count += 1
            if limit and count >= limit:
                return

def resolve_selected_papers(input_jsonl: Optional[str]) -> Path:
    """
    If user passes --papers-jsonl, use that; else read latest pointer from get_papers.
    """
    if input_jsonl:
        p = Path(input_jsonl).resolve()
        if not p.exists():
            raise FileNotFoundError(f"--papers-jsonl not found: {p}")
        return p

    latest = PROJECT_ROOT / "data" / "ingest" / "runs" / "latest.json"
    if not latest.exists():
        raise FileNotFoundError(f"Latest pointer not found: {latest}")
    with open(latest, "r", encoding="utf-8") as f:
        meta = json.load(f)
    papers_path = meta.get("papers_path")
    if not papers_path:
        raise RuntimeError("latest.json missing 'papers_path'")
    # Helper: map Windows path to WSL POSIX if needed
    def _windows_to_wsl(path_str: str) -> Optional[Path]:
        try:
            if ":" in path_str and "\\" in path_str:
                drive = path_str.split(":", 1)[0].lower()
                rest = path_str.split(":", 1)[1].lstrip("\\/")
                rest = rest.replace("\\", "/")
                return Path(f"/mnt/{drive}/{rest}")
        except Exception:
            return None
        return None

    # Base resolution: honor EF_PROJECT_ROOT if provided
    ef_root = os.environ.get("EF_PROJECT_ROOT")
    base_root = Path(ef_root) if ef_root else PROJECT_ROOT

    p = Path(papers_path)
    if not p.is_absolute():
        p = (base_root / p).resolve()
    # If not found, attempt Windows→WSL translation
    if not p.exists():
        alt = _windows_to_wsl(papers_path)
        if alt and alt.exists():
            return alt
        # Also try replacing the project root via EF_PROJECT_ROOT when pointer was absolute
        if ef_root and ":" in papers_path and "\\" in papers_path:
            # Attempt to rebase relative path under EF_PROJECT_ROOT
            try:
                # Find the first occurrence of the repo directory name to slice from
                marker = "evidentfit"
                idx = papers_path.lower().find(marker)
                if idx != -1:
                    rel = papers_path[idx+len(marker):].lstrip("\\/")
                    candidate = Path(ef_root) / rel.replace("\\", "/")
                    if candidate.exists():
                        return candidate
            except Exception:
                pass
        raise FileNotFoundError(f"Papers JSONL not found: {p}")
    return p

# --- Chunking utilities (approx 4 chars/token, with headroom for prompt/output) ---

def _char_budget(ctx_tokens: int, max_new_tokens: int) -> int:
    # Reserve ~1024 tokens for prompt/system + output budget
    safe_input_tokens = max(512, ctx_tokens - max_new_tokens - 1024)
    return max(1000, safe_input_tokens * 4)  # ~4 chars/token

def _split_text_safely(text: str, ctx_tokens: int, max_new_tokens: int) -> List[str]:
    if not text:
        return []
    budget = _char_budget(ctx_tokens, max_new_tokens)
    n = len(text)
    i = 0
    chunks: List[str] = []
    
    while i < n:
        j = min(n, i + budget)
        
        # Smart boundary detection with priority order
        boundary_candidates = []
        
        # 1. Double newlines (paragraph breaks) - highest priority
        para_break = text.rfind("\n\n", i, j)
        if para_break > i + 100:  # Ensure meaningful chunk size
            boundary_candidates.append(("paragraph", para_break))
        
        # 2. Section headers (common patterns)
        section_patterns = ["\nIntroduction", "\nMethods", "\nResults", "\nDiscussion", "\nConclusion"]
        for pattern in section_patterns:
            section_pos = text.rfind(pattern, i, j)
            if section_pos > i + 100:
                boundary_candidates.append(("section", section_pos))
        
        # 3. Sentence boundaries
        sent_break = text.rfind(". ", i, j)
        if sent_break > i + 200:  # Ensure reasonable chunk size
            boundary_candidates.append(("sentence", sent_break))
        
        # 4. Word boundaries (fallback)
        word_break = text.rfind(" ", i, j)
        if word_break > i + 300:
            boundary_candidates.append(("word", word_break))
        
        # Choose the best boundary
        if boundary_candidates:
            # Prefer paragraph > section > sentence > word
            boundary_type, k = max(boundary_candidates, key=lambda x: (
                {"paragraph": 4, "section": 3, "sentence": 2, "word": 1}[x[0]], x[1]
            ))
        else:
            k = j  # No good boundary found, use full budget
        
        chunk = text[i:k].strip()
        if chunk and len(chunk) > 50:  # Only include substantial chunks
            chunks.append(chunk)
        
        # Move past the boundary, with some overlap for context preservation
        if k < n and boundary_type in ["paragraph", "section"]:
            i = k + 1  # Minimal overlap for structural breaks
        else:
            i = k  # No overlap for sentence/word breaks
    
    return chunks

def _merge_chunk_summaries(doc_meta: Dict[str, Any], chunk_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge N normalized chunk summaries into one doc-level record.
    Strategy: prefer first chunk's scalar fields; concatenate/union list fields.
    """
    if not chunk_summaries:
        return {}

    first = dict(chunk_summaries[0])
    lists_to_union = ["key_findings", "limitations", "keywords", "relevance_tags"]
    measures = ["strength", "endurance", "power"]

    # Union list fields
    for k in lists_to_union:
        acc = []
        for s in chunk_summaries:
            vals = s.get(k) or []
            if isinstance(vals, list):
                acc.extend(vals)
        first[k] = list(dict.fromkeys([v for v in acc if v]))

    # Outcome measures union
    om_acc: Dict[str, List[str]] = {m: [] for m in measures}
    for s in chunk_summaries:
        om = (s.get("outcome_measures") or {})
        for m in measures:
            arr = om.get(m) or []
            if isinstance(arr, list):
                om_acc[m].extend(arr)
    first["outcome_measures"] = {m: list(dict.fromkeys([v for v in om_acc[m] if v])) for m in measures}

    # Supplements union
    supp_acc: List[str] = []
    for s in chunk_summaries:
        arr = s.get("supplements") or []
        if isinstance(arr, list):
            supp_acc.extend(arr)
    first["supplements"] = list(dict.fromkeys([v for v in supp_acc if v]))

    # Summary merge
    if not (first.get("summary") or "").strip():
        summaries = [s.get("summary", "") for s in chunk_summaries if s.get("summary")]
        first["summary"] = " ".join(summaries)[:1200]

    # Carry doc meta back
    first["pmid"] = doc_meta.get("pmid")
    first["doi"] = doc_meta.get("doi")
    first["title"] = doc_meta.get("title") or first.get("title")
    first["journal"] = doc_meta.get("journal") or first.get("journal")
    first["year"] = doc_meta.get("year") or first.get("year")

    # Normalize again for safety
    return normalize_data(first)

# -------------------------
# Main
# -------------------------

def main():
    ap = argparse.ArgumentParser(description="EvidentFit paper processor (streaming + resume)")
    ap.add_argument("--papers-jsonl", type=str, help="Path to pm_papers.jsonl (optional; defaults to runs/latest.json pointer)")
    ap.add_argument("--max-papers", type=int, default=200, help="Max papers to process")
    ap.add_argument("--batch-size", type=int, default=1, help="Keep small to cap VRAM")
    ap.add_argument("--microbatch-size", type=int, default=1)
    ap.add_argument("--ctx-tokens", type=int, default=16384)
    ap.add_argument("--max-new-tokens", type=int, default=640)
    # Model: default will be resolved after parsing to prefer a local path if present
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--temperature", type=float, default=0.0, help="0.0 for deterministic output; >0 enables sampling")
    ap.add_argument("--seed", type=int, default=None, help="Global RNG seed for reproducibility")
    ap.add_argument("--resume-summaries", type=str, default=None, help="Path to an existing summaries .jsonl or .jsonl.tmp to resume into (legacy; prefer streaming to master)")
    ap.add_argument("--master-summaries", type=str, default=None, help="Path to master summaries file (default: $EF_MASTER_SUMMARIES or data/paper_processor/master/summaries_master.jsonl)")
    # Progress + backoff tuning
    ap.add_argument("--pointer-interval", type=int, default=20, help="How often (in input papers) to refresh data/paper_processor/latest.json")
    ap.add_argument("--log-interval", type=int, default=100, help="How often (in successful outputs) to log progress")
    ap.add_argument("--max-abstract-chars", type=int, default=20000, help="Clamp abstract/content length before chunking")
    ap.add_argument("--slow-threshold-sec", type=float, default=60.0, help="Threshold in seconds to consider a paper slow")
    ap.add_argument("--slow-backoff-sec", type=float, default=1.0, help="Sleep duration after a slow paper (seconds)")
    ap.add_argument("--exception-backoff-sec", type=float, default=2.0, help="Sleep duration after an exception (seconds)")
    ap.add_argument("--preflight-only", action="store_true", help="Run preflight validation only, don't process papers")
    args = ap.parse_args()
    
    # Unified streaming mode: always append to master
    run_id = f"paper_processor_stream_{int(time.time())}"
    setup_logging()
    LOG.info("=" * 80)
    LOG.info("PAPER PROCESSOR START (STREAM-TO-MASTER)")
    LOG.info("=" * 80)
    LOG.info(f"Run ID: {run_id}")
    LOG.info("Mode: stream-to-master")

    papers_jsonl = resolve_selected_papers(args.papers_jsonl)
    LOG.info(f"Selected papers: {papers_jsonl}")
    
    # Set canonical path for collect bundles (same as papers_jsonl)
    canonical_path = Path(papers_jsonl)
    # Log database connection for clarity
    try:
        dsn = os.environ.get('EVIDENTFIT_DB_DSN', 'Not set')
        LOG.info(f"Database DSN: {dsn.replace('Winston8891**', '***')}")
    except Exception as e:
        LOG.warning(f"Could not get database DSN: {e}")

    # Optional preflight validation before expensive model load
    if args.preflight_only:
        LOG.info("Running preflight-only validation against database...")
        total = 0
        db_full = 0
        db_abs = 0
        db_missing_local = 0
        db_no_text_local = 0
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            total += 1
            pmid_val = p.get("pmid")
            if not pmid_val:
                db_missing_local += 1
                continue
            
            try:
                # Convert PMID to database format
                db_pmid = str(pmid_val)
                if not db_pmid.startswith('pmid_'):
                    db_pmid = f"pmid_{db_pmid}"
                
                # Try to get bundle
                bundle = build_section_bundle(db_pmid, canonical_path)
                if not bundle or not bundle.sections:
                    db_missing_local += 1
                    continue
                
                # Check if has fulltext
                has_fulltext = bundle.stats.get("has_fulltext", False)
                if has_fulltext:
                    db_full += 1
                else:
                    # Check if has abstract
                    abstract_data = bundle.sections.get("abstract", {})
                    abstract_text = abstract_data.get("text", "").strip()
                    if abstract_text:
                        db_abs += 1
                    else:
                        db_no_text_local += 1
                        
            except Exception as e:
                LOG.warning(f"Preflight error for PMID {pmid_val}: {e}")
                db_missing_local += 1
                continue
                
        LOG.info(f"Preflight: total={total}, db_fulltext={db_full}, db_abstract={db_abs}, db_missing={db_missing_local}, db_no_text={db_no_text_local}")
        print(f"Preflight complete. total={total}, fulltext={db_full}, abstract={db_abs}, missing={db_missing_local}, no_text={db_no_text_local}")
        return

    # Resolve default model preference: prefer local directory if available
    if not args.model:
        # Environment overrides
        env_model = os.environ.get("EF_MODEL_PATH") or os.environ.get("MODEL_LOCAL_DIR")
        candidates = []
        if env_model:
            candidates.append(Path(env_model))
        # Common local paths
        candidates.append(Path("E:/models/Mistral-7B-Instruct-v0.3"))
        candidates.append(Path("E:\\models\\Mistral-7B-Instruct-v0.3"))
        candidates.append(PROJECT_ROOT / "models" / "Mistral-7B-Instruct-v0.3")

        chosen = None
        for c in candidates:
            try:
                if c and Path(c).exists():
                    chosen = str(Path(c).resolve())
                    break
            except Exception:
                continue
        if chosen:
            args.model = chosen
            LOG.info(f"Model resolved to local path: {args.model}")
        else:
            args.model = "mistralai/Mistral-7B-Instruct-v0.3"
            LOG.info(f"Model resolved to remote repo: {args.model}")

    client = MistralClient(model_name=args.model)

    storage = StorageManager()
    storage.initialize()

    # Resolve master path, load dedupe, open appender
    env_master = os.environ.get("EF_MASTER_SUMMARIES")
    default_master = PROJECT_ROOT / "data" / "paper_processor" / "master" / "summaries_master.jsonl"
    master_path = Path(args.master_summaries) if args.master_summaries else (Path(env_master) if env_master else default_master)
    master_path.parent.mkdir(parents=True, exist_ok=True)
    if not master_path.exists():
        open(master_path, "w", encoding="utf-8").close()
        LOG.info(f"Initialized master summaries: {master_path}")
    LOG.info(f"Master summaries: {master_path}")

    seen_keys = storage.load_master_dedupe_keys(master_path)
    LOG.info(f"Loaded {len(seen_keys):,} dedupe keys from master")
    with open(master_path, "r", encoding="utf-8") as f:
        master_size_before = sum(1 for line in f if line.strip())
    LOG.info(f"Master size before: {master_size_before:,} papers")

    storage.open_summaries_appender(master_path)

    # Telemetry counters
    papers_in = 0
    papers_out = 0
    skipped_empty = 0
    skipped_dedup = 0
    chunks_total = 0
    per_paper_latency: List[float] = []
    
    # NEW: Enhanced tracking (store-only)
    failed_papers: List[Dict[str, Any]] = []
    slow_papers: List[Dict[str, Any]] = []
    
    # Enhanced metrics tracking
    batch_processing_used = 0
    individual_processing_used = 0
    llm_success_count = 0
    llm_fallback_count = 0
    chunk_processing_errors = 0
    retry_attempts_total = 0
    gpu_memory_usage: List[float] = []
    processing_modes = {"batch": 0, "individual": 0, "heuristics_only": 0}

    # Skip reason breakdown for clarity and resumability audits
    skipped_no_text = 0            # neither fulltext nor abstract/content present
    skipped_too_short = 0          # present but too short to be meaningful
    skipped_no_chunks = 0          # chunking produced zero chunks (after both sources considered)

    # On-the-fly aggregate stats
    year_values: List[int] = []
    study_type_counts = Counter()
    # evidence_grade removed
    supplement_counts = Counter()

    # Monthly upgrade tracking: prior abstract-only -> now fulltext
    upgrade_candidates: List[Dict[str, Any]] = []

    # Fulltext store diagnostics (store-only inputs)
    store_fulltext_used = 0
    store_abstract_used = 0
    store_missing = 0
    store_no_text = 0

    start = time.time()

    # Graceful shutdown handling (SIGINT/SIGTERM)
    shutdown_requested = False
    def _handle_signal(signum, frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        try:
            tmp_path, final_path = storage.get_current_writer_paths()
            if tmp_path or final_path:
                storage.update_latest_pointer((tmp_path or final_path))
        except Exception:
            pass
        LOG.warning(f"Received signal {signum}; will stop after current paper.")
    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        # Not all platforms support SIGTERM (e.g., Windows older shells)
        pass

    try:
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            papers_in += 1
            t0 = time.time()

            # Collect bundle selection: PMID -> collect bundles from database
            pmid_val = p.get("pmid")
            if not pmid_val:
                store_missing += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning(f"No PMID found for paper")
                continue

            try:
                # Convert PMID to database format (add pmid_ prefix if not present)
                db_pmid = str(pmid_val)
                if not db_pmid.startswith('pmid_'):
                    db_pmid = f"pmid_{db_pmid}"
                
                # Use build_section_bundle to get structured content
                bundle = build_section_bundle(db_pmid, canonical_path)
                if not bundle or not bundle.sections:
                    store_missing += 1
                    skipped_empty += 1
                    skipped_no_text += 1
                    LOG.warning(f"No bundle found for PMID {pmid_val}")
                    continue

                # Determine content source and build content
                content_source = None  # "fulltext" | "abstract"
                content = ""
                
                # Check if we have fulltext sections (methods, results, discussion)
                has_fulltext = bundle.stats.get("has_fulltext", False)
                
                if has_fulltext:
                    # Build fulltext content from sections
                    content_parts = []
                    for section in ["abstract", "methods", "results", "discussion"]:
                        section_data = bundle.sections.get(section, {})
                        section_text = section_data.get("text", "").strip()
                        if section_text:
                            content_parts.append(f"## {section.title()}\n{section_text}")
                    
                    content = "\n\n".join(content_parts)
                    content_source = "fulltext"
                    store_fulltext_used += 1
                else:
                    # Fall back to abstract only
                    abstract_data = bundle.sections.get("abstract", {})
                    abstract_text = abstract_data.get("text", "").strip()
                    if abstract_text:
                        if len(abstract_text) > args.max_abstract_chars:
                            abstract_text = abstract_text[:args.max_abstract_chars]
                        content = abstract_text
                        content_source = "abstract"
                        store_abstract_used += 1
                    else:
                        store_no_text += 1
                        skipped_empty += 1
                        skipped_no_text += 1
                        LOG.warning(f"No content found for PMID {pmid_val}")
                        continue

                if len(content) < 20:
                    skipped_empty += 1
                    skipped_too_short += 1
                    continue

            except Exception as e:
                store_missing += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning(f"Error collecting bundle for PMID {pmid_val}: {e}")
                continue

            dkey = create_dedupe_key(p)
            if dkey in seen_keys:
                # If monthly mode and we have new fulltext while master had abstract-only, capture upgrade
                if hasattr(args, 'mode') and args.mode == "monthly":
                    # Note: master_input_source tracking would need to be implemented for upgrade detection
                    prior_src = "unknown"
                    now_has_full = (content_source == "fulltext")
                    if prior_src == "abstract" and now_has_full:
                        upgrade_candidates.append({
                            "dedupe_key": dkey,
                            "pmid": p.get("pmid"),
                            "doi": p.get("doi"),
                            "title": (p.get("title") or "")[:160],
                            "previous_source": prior_src,
                            "new_source": content_source,
                        })
                skipped_dedup += 1
                continue
            seen_keys.add(dkey)
            
            # Chunk
            chunks = _split_text_safely(content, args.ctx_tokens, args.max_new_tokens)
            if not chunks:
                # If fulltext produced no chunks, attempt abstract fallback
                if content_source == "fulltext" and abstract_text:
                    content = abstract_text
                    content_source = "abstract"
                    chunks = _split_text_safely(content, args.ctx_tokens, args.max_new_tokens)
                if not chunks:
                    skipped_empty += 1
                    skipped_no_chunks += 1
                    continue
            chunks_total += len(chunks)

            # Prepare chunk inputs
            chunk_inputs = []
            for c_idx, ctext in enumerate(chunks):
                cp = dict(p)
                cp["content"] = ctext
                cp["chunk_idx"] = c_idx
                cp["chunk_total"] = len(chunks)
                chunk_inputs.append(cp)

            # Inference with batch processing for efficiency
            try:
                chunk_summaries = []
                max_retries = 2
                
                # Use batch processing if we have multiple chunks and batch_size > 1
                if len(chunk_inputs) > 1 and args.batch_size > 1:
                    processing_modes["batch"] += 1
                    try:
                        from .extract import _llm_enrich
                        from .mistral_client import MistralClient
                        
                        # Prepare bundles for batch processing
                        bundles = []
                        for chunk_input in chunk_inputs:
                            bundle = {
                                "meta": {
                                    "pmid": chunk_input.get("pmid"),
                                    "doi": chunk_input.get("doi"),
                                    "title": chunk_input.get("title"),
                                    "journal": chunk_input.get("journal"),
                                    "year": chunk_input.get("year"),
                                    "supplements": chunk_input.get("supplements", []),
                                    "primary_goal": chunk_input.get("primary_goal", "general")
                                },
                                "sections": {
                                    "abstract": {"text": chunk_input.get("content", "")},
                                    "results": {"text": ""},
                                    "methods": {"text": ""},
                                    "discussion": {"text": ""}
                                }
                            }
                            bundles.append(bundle)
                        
                        # Try batch processing
                        client = MistralClient(model_name=args.model)
                        prompt_path = Path("agents/paper_processor/prompts/card_extractor_v1.txt")
                        prompt = prompt_path.read_text(encoding="utf-8")
                        
                        user_prompts = []
                        for bundle in bundles:
                            abstract = bundle["sections"]["abstract"]["text"]
                            context = f"ABSTRACT:\n{abstract}"
                            usermsg = prompt.replace("{{CONTEXT}}", context)[:12000]
                            user_prompts.append(usermsg)
                        
                        sysmsg = "You are an expert evidence extraction engine. Output strict JSON only."
                        batch_results = client.generate_batch_json(
                            system_prompt=sysmsg,
                            user_prompts=user_prompts,
                            max_new_tokens=1024,
                            temperature=args.temperature,
                            batch_size=min(args.batch_size, len(chunk_inputs))
                        )
                        
                        # Convert batch results to cards
                        for i, (bundle, result) in enumerate(zip(bundles, batch_results)):
                            if result:
                                # Merge LLM result with heuristics
                                from .extract import _heuristics
                                heuristics_result = _heuristics(bundle)
                                card = {**heuristics_result, **result}
                                chunk_summaries.append(normalize_data(card))
                                llm_success_count += 1
                            else:
                                # Fallback to heuristics only
                                from .extract import _heuristics
                                card = _heuristics(bundle)
                                chunk_summaries.append(normalize_data(card))
                                llm_fallback_count += 1
                                processing_modes["heuristics_only"] += 1
                        
                    except Exception as batch_error:
                        LOG.warning(f"Batch processing failed for PMID {p.get('pmid')}, falling back to individual processing: {batch_error}")
                        # Fall back to individual processing
                        chunk_inputs = chunk_inputs  # Continue with individual processing below
                
                # Individual processing (fallback or when batch_size = 1)
                if not chunk_summaries:
                    processing_modes["individual"] += 1
                    for chunk_input in chunk_inputs:
                        # Create a minimal bundle structure for the extract module
                        bundle = {
                            "meta": {
                                "pmid": chunk_input.get("pmid"),
                                "doi": chunk_input.get("doi"),
                                "title": chunk_input.get("title"),
                                "journal": chunk_input.get("journal"),
                                "year": chunk_input.get("year"),
                                "supplements": chunk_input.get("supplements", []),
                                "primary_goal": chunk_input.get("primary_goal", "general")
                            },
                            "sections": {
                                "abstract": {"text": chunk_input.get("content", "")},
                                "results": {"text": ""},
                                "methods": {"text": ""},
                                "discussion": {"text": ""}
                            }
                        }
                        
                        # Retry logic for individual chunks
                        card = None
                        for attempt in range(max_retries + 1):
                            try:
                                from .extract import build_card
                                card = build_card(
                                    bundle=bundle,
                                    model_ver=args.model,
                                    prompt_ver="v1",
                                    llm_mode="fallback",
                                    metrics_path=None
                                )
                                llm_success_count += 1
                                break  # Success, exit retry loop
                            except Exception as chunk_error:
                                retry_attempts_total += 1
                                if attempt < max_retries:
                                    LOG.warning(f"Chunk processing attempt {attempt + 1} failed for PMID {p.get('pmid')}, retrying: {chunk_error}")
                                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                                else:
                                    LOG.error(f"All chunk processing attempts failed for PMID {p.get('pmid')}: {chunk_error}")
                                    chunk_processing_errors += 1
                                    llm_fallback_count += 1
                                    processing_modes["heuristics_only"] += 1
                                    # Create a minimal fallback card
                                    card = normalize_data({
                                        "pmid": chunk_input.get("pmid"),
                                        "title": chunk_input.get("title", "Processing failed"),
                                        "summary": "Processing failed due to LLM error",
                                        "supplements": chunk_input.get("supplements", []),
                                        "study_type": "unknown"
                                    })
                        
                        if card:
                            chunk_summaries.append(card)
            except Exception as e:
                LOG.exception(f"Generation failed for PMID {p.get('pmid')}: {e}")
                # Backoff to ease GPU/IO pressure
                try:
                    time.sleep(max(0.0, float(args.exception_backoff_sec)))
                except Exception:
                    pass
                # Attempt abstract fallback if we were on fulltext
                if content_source == "fulltext" and abstract_text:
                    try:
                        content = abstract_text
                        content_source = "abstract"
                        chunks = _split_text_safely(content, args.ctx_tokens, args.max_new_tokens)
                        if not chunks:
                            skipped_empty += 1
                            skipped_no_chunks += 1
                            failed_papers.append({
                                "pmid": p.get("pmid"),
                                "doi": p.get("doi"),
                                "title": p.get("title", "")[:100],
                                "reason": "no_chunks_after_exception_then_abstract",
                            })
                            continue
                        chunk_inputs = []
                        for c_idx, ctext in enumerate(chunks):
                            cp = dict(p)
                            cp["content"] = ctext
                            cp["chunk_idx"] = c_idx
                            cp["chunk_total"] = len(chunks)
                            chunk_inputs.append(cp)
                        chunk_summaries = []
                        for chunk_input in chunk_inputs:
                            bundle = {
                                "meta": {
                                    "pmid": chunk_input.get("pmid"),
                                    "doi": chunk_input.get("doi"),
                                    "title": chunk_input.get("title"),
                                    "journal": chunk_input.get("journal"),
                                    "year": chunk_input.get("year"),
                                    "supplements": chunk_input.get("supplements", []),
                                    "primary_goal": chunk_input.get("primary_goal", "general")
                                },
                                "sections": {
                                    "abstract": {"text": chunk_input.get("content", "")},
                                    "results": {"text": ""},
                                    "methods": {"text": ""},
                                    "discussion": {"text": ""}
                                }
                            }
                            card = build_card(
                                bundle=bundle,
                                model_ver=args.model,
                                prompt_ver="v1",
                                llm_mode="fallback",
                                metrics_path=None
                            )
                            chunk_summaries.append(card)
                    except Exception as e2:
                        LOG.exception(f"Fallback generation (abstract) also failed for PMID {p.get('pmid')}: {e2}")
                        failed_papers.append({
                            "pmid": p.get("pmid"),
                            "doi": p.get("doi"),
                            "title": p.get("title", "")[:100],
                            "reason": "exception_generation_both_sources",
                        })
                        try:
                            time.sleep(max(0.0, float(args.exception_backoff_sec)))
                        except Exception:
                            pass
                        continue
                else:
                    failed_papers.append({
                        "pmid": p.get("pmid"),
                        "doi": p.get("doi"),
                        "title": p.get("title", "")[:100],
                        "reason": "exception_generation",
                    })
                    try:
                        time.sleep(max(0.0, float(args.exception_backoff_sec)))
                    except Exception:
                        pass
                    continue

            # Normalize/validate chunks
            norm_chunks: List[Dict[str, Any]] = []
            for s in chunk_summaries:
                try:
                    s = normalize_data(s)
                    if not validate_optimized_schema(s):
                        LOG.debug("Schema validation failed for a chunk (continuing).")
                    norm_chunks.append(s)
                except Exception:
                    continue

            # Fallback to abstract if fulltext path produced no valid chunks
            if not norm_chunks and content_source == "fulltext" and abstract_text:
                LOG.info(f"Fulltext failed validation; attempting abstract fallback for PMID {p.get('pmid')}")
                # Re-run on abstract
                content = abstract_text
                content_source = "abstract"
                chunks = _split_text_safely(content, args.ctx_tokens, args.max_new_tokens)
                if not chunks:
                    skipped_empty += 1
                    skipped_no_chunks += 1
                    failed_papers.append({
                        "pmid": p.get("pmid"),
                        "doi": p.get("doi"),
                        "title": p.get("title", "")[:100],
                        "reason": "no_chunks_after_fulltext_then_abstract",
                        "chunks_attempted": 0
                    })
                    continue
                chunk_inputs = []
                for c_idx, ctext in enumerate(chunks):
                    cp = dict(p)
                    cp["content"] = ctext
                    cp["chunk_idx"] = c_idx
                    cp["chunk_total"] = len(chunks)
                    chunk_inputs.append(cp)
                chunk_summaries = []
                for chunk_input in chunk_inputs:
                    bundle = {
                        "meta": {
                            "pmid": chunk_input.get("pmid"),
                            "doi": chunk_input.get("doi"),
                            "title": chunk_input.get("title"),
                            "journal": chunk_input.get("journal"),
                            "year": chunk_input.get("year"),
                            "supplements": chunk_input.get("supplements", []),
                            "primary_goal": chunk_input.get("primary_goal", "general")
                        },
                        "sections": {
                            "abstract": {"text": chunk_input.get("content", "")},
                            "results": {"text": ""},
                            "methods": {"text": ""},
                            "discussion": {"text": ""}
                        }
                    }
                    card = build_card(
                        bundle=bundle,
                        model_ver=args.model,
                        prompt_ver="v1",
                        llm_mode="fallback",
                        metrics_path=None
                    )
                    chunk_summaries.append(card)
                norm_chunks = []
                for s in chunk_summaries:
                    try:
                        s = normalize_data(s)
                        if not validate_optimized_schema(s):
                            LOG.debug("Schema validation failed for a chunk (continuing).")
                        norm_chunks.append(s)
                    except Exception:
                        continue

            if not norm_chunks:
                LOG.warning(f"All chunks failed validation - Paper: {p.get('pmid')} - {p.get('title', '')[:60]}")
                failed_papers.append({
                    "pmid": p.get("pmid"),
                    "doi": p.get("doi"),
                    "title": p.get("title", "")[:100],
                    "reason": "all_chunks_failed_validation",
                    "chunks_attempted": len(chunk_summaries) if chunk_summaries else 0
                })
                continue

            merged = _merge_chunk_summaries(
                {"pmid": p.get("pmid"), "doi": p.get("doi"), "title": p.get("title"), "journal": p.get("journal"), "year": p.get("year")},
                norm_chunks,
            )

            # Derive quality_score from pm_papers without clamping: prefer relevance_score, then reliability_score, then study_design_score
            try:
                qsource = None
                for key in ("relevance_score", "reliability_score", "study_design_score"):
                    if p.get(key) is not None:
                        qsource = float(p.get(key))
                        break
                if qsource is not None:
                    merged["quality_score"] = qsource
                else:
                    merged.pop("quality_score", None)
            except Exception:
                merged.pop("quality_score", None)

            # Remove evidence_grade entirely from outputs
            merged.pop("evidence_grade", None)

            # Annotate provenance for downstream audits
            merged["input_source"] = content_source  # "fulltext" or "abstract"
            merged["input_chars"] = len(content)

            # Always append to master and track for delta
            storage.write_summary_line_monthly(merged)
            papers_out += 1

            # Usage counters are already tracked via store_fulltext_used/store_abstract_used
            
            paper_elapsed = time.time() - t0
            per_paper_latency.append(paper_elapsed)
            
            # Update aggregates for stats
            y = merged.get("year")
            if isinstance(y, int):
                year_values.append(y)
            st = merged.get("study_type", "unknown")
            study_type_counts[st] += 1
            for s in (merged.get("supplements") or []):
                if s:
                    supplement_counts[s] += 1
            
            # Performance monitoring: Track slow papers
            if paper_elapsed > args.slow_threshold_sec:  # configurable
                slow_papers.append({
                    "pmid": p.get("pmid"),
                    "title": p.get("title", "")[:100],
                    "elapsed_sec": round(paper_elapsed, 2),
                    "chunks": len(chunks),
                    "content_chars": len(content)
                })
                LOG.warning(f"Slow paper detected: {p.get('pmid')} took {paper_elapsed:.1f}s ({len(chunks)} chunks, {len(content):,} chars)")
                # Backoff after slow item
                try:
                    time.sleep(max(0.0, float(args.slow_backoff_sec)))
                except Exception:
                    pass
            
            # Progress reporting: configurable interval
            if papers_out % max(1, args.log_interval) == 0:
                elapsed = time.time() - start
                rate = papers_out / elapsed if elapsed > 0 else 0
                remaining_papers = args.max_papers - papers_out
                eta_sec = remaining_papers / rate if rate > 0 else 0
                eta_hours = eta_sec / 3600
                progress_pct = (papers_out / args.max_papers * 100) if args.max_papers > 0 else 0
                
                LOG.info(f"PROGRESS: {papers_out}/{args.max_papers} papers ({progress_pct:.1f}%) | "
                        f"Rate: {rate*60:.1f} papers/min | "
                        f"ETA: {eta_hours:.1f}h | "
                        f"Full-text (store): {store_fulltext_used}/{papers_out} ({(store_fulltext_used/papers_out*100) if papers_out else 0.0:.1f}%)")

            if torch.cuda.is_available() and (idx % max(1, args.batch_size) == 0):
                torch.cuda.empty_cache()
                # Track GPU memory usage
                try:
                    gpu_memory = torch.cuda.memory_allocated() / 1024**3  # GB
                    gpu_memory_usage.append(gpu_memory)
                except Exception:
                    pass

            # Periodically update latest pointer to the active tmp path to aid resume
            if idx % max(1, args.pointer_interval) == 0:
                tmp_path, final_path = storage.get_current_writer_paths()
                if tmp_path or final_path:
                    storage.update_latest_pointer((tmp_path or final_path))

            # Check for graceful shutdown request
            if shutdown_requested:
                LOG.info("Shutdown requested; stopping after current paper.")
                break

        final_summaries_path = storage.close_summaries_writer()

        # Calculate master size after, save delta, rebuild index
        master_size_after = 0
        delta_path = None
        index_path = None
        # Count master size after appending
        with open(master_path, "r", encoding="utf-8") as f:
            master_size_after = sum(1 for line in f if line.strip())
        LOG.info(f"Master size after: {master_size_after:,} papers (+{master_size_after - master_size_before:,})")

        # Rebuild master index
        LOG.info("Rebuilding master index...")
        index = storage.build_master_index(master_path)
        index_path = storage.save_master_index(index, master_path)
        LOG.info(f"Master index saved: {index_path} ({len(index):,} entries)")

        # Validate master
        LOG.info("Validating master...")
        valid, errors = storage.validate_master(master_path, index_path)
        if not valid:
            LOG.error(f"Master validation failed: {errors}")
            LOG.error("Consider restoring from backup!")
        else:
            LOG.info("Master validation passed")

        elapsed = time.time() - start
        stats = {
            "run_id": run_id,
            "mode": "stream_to_master",
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
            
            # Chunking stats
            "chunks_total": chunks_total,
            "avg_chunks_per_doc": (chunks_total / papers_out) if papers_out else 0.0,

            # Skip breakdown
            "skipped_no_text": skipped_no_text,
            "skipped_too_short": skipped_too_short,
            "skipped_no_chunks": skipped_no_chunks,

            # Fulltext store diagnostics
            "store_fulltext_used": store_fulltext_used,
            "store_abstract_used": store_abstract_used,
            "store_missing": store_missing,
            "store_no_text": store_no_text,
            
            # Timing stats
            "elapsed_sec": elapsed,
            "elapsed_hours": elapsed / 3600,
            "rate_papers_per_sec": (papers_out / elapsed) if elapsed > 0 else None,
            "rate_papers_per_min": (papers_out / elapsed * 60) if elapsed > 0 else None,
            "median_latency_sec": (sorted(per_paper_latency)[len(per_paper_latency)//2] if per_paper_latency else None),
            "min_latency_sec": min(per_paper_latency) if per_paper_latency else None,
            "max_latency_sec": max(per_paper_latency) if per_paper_latency else None,
            
            # Model config
            "model": args.model,
            "ctx_tokens": args.ctx_tokens,
            "max_new_tokens": args.max_new_tokens,
            "batch_size": args.batch_size,
            # Runtime config for audits
            "pointer_interval": args.pointer_interval,
            "log_interval": args.log_interval,
            "max_abstract_chars": args.max_abstract_chars,
            "slow_threshold_sec": args.slow_threshold_sec,
            "slow_backoff_sec": args.slow_backoff_sec,
            "exception_backoff_sec": args.exception_backoff_sec,
            
            # Enhanced metrics
            "processing_modes": processing_modes,
            "llm_success_count": llm_success_count,
            "llm_fallback_count": llm_fallback_count,
            "chunk_processing_errors": chunk_processing_errors,
            "retry_attempts_total": retry_attempts_total,
            "gpu_memory_stats": {
                "max_gb": max(gpu_memory_usage) if gpu_memory_usage else 0,
                "avg_gb": sum(gpu_memory_usage) / len(gpu_memory_usage) if gpu_memory_usage else 0,
                "samples": len(gpu_memory_usage)
            },
            
            # Index stats (no evidence_grade aggregation)
            "index_stats": {
                "total_papers": papers_out,
                "study_types": dict(study_type_counts),
                "year_range": {
                    "min": min(year_values) if year_values else None,
                    "max": max(year_values) if year_values else None,
                },
                "supplements": dict(supplement_counts),
            },
            "summaries_path": str(final_summaries_path.as_posix()),
        }
        stats["master_size_before"] = master_size_before
        stats["master_size_after"] = master_size_after
        stats["net_additions"] = master_size_after - master_size_before
        stats["master_index_path"] = str(index_path.as_posix()) if index_path else None
        
        storage.save_processing_stats(stats)
        
        # Save delta for this run by default
        LOG.info("Saving run delta...")
        delta_path = storage.save_monthly_delta(stats)
        LOG.info(f"Run delta saved: {delta_path}")
        
        LOG.info("Done.")
        
        # Enhanced final summary
        print("\n" + "=" * 80)
        print(f"PAPER PROCESSOR COMPLETE (STREAM-TO-MASTER)")
        print("=" * 80)
        print(f"Papers: {papers_out} successful / {papers_in} total ({papers_out/papers_in*100:.1f}%)")
        print(f"Skipped: {skipped_empty} empty, {skipped_dedup} duplicates")
        print(f"Failed: {len(failed_papers)} papers ({len(failed_papers)/papers_in*100:.1f}%)")
        
        print(f"\nMaster Corpus:")
        print(f"  Before: {master_size_before:,} papers")
        print(f"  After: {master_size_after:,} papers")
        print(f"  Added: {master_size_after - master_size_before:,} papers")
        
        print(f"\nFull-text (store): {store_fulltext_used}/{papers_out} ({(store_fulltext_used/papers_out*100) if papers_out else 0.0:.1f}%)")
        print(f"Abstract (store): {store_abstract_used}/{papers_out} ({(store_abstract_used/papers_out*100) if papers_out else 0.0:.1f}%)")
        print(f"Skipped (no text available): {skipped_no_text}")
        print(f"\nChunking: {chunks_total} total chunks, avg {chunks_total/papers_out:.2f} per paper")
        print(f"Slow papers (>60s): {len(slow_papers)}/{papers_out} ({len(slow_papers)/papers_out*100:.1f}%)")
        print(f"\nProcessing Modes:")
        print(f"  Batch: {processing_modes['batch']} papers")
        print(f"  Individual: {processing_modes['individual']} papers") 
        print(f"  Heuristics-only: {processing_modes['heuristics_only']} papers")
        print(f"\nLLM Performance:")
        print(f"  Success: {llm_success_count} chunks")
        print(f"  Fallback: {llm_fallback_count} chunks")
        print(f"  Errors: {chunk_processing_errors} chunks")
        print(f"  Retries: {retry_attempts_total} attempts")
        if gpu_memory_usage:
            print(f"\nGPU Memory: max={max(gpu_memory_usage):.1f}GB, avg={sum(gpu_memory_usage)/len(gpu_memory_usage):.1f}GB")
        print(f"\nTime: {elapsed/3600:.2f} hours ({papers_out/elapsed*60:.1f} papers/min)")
        print(f"Latency: min={min(per_paper_latency) if per_paper_latency else 0:.1f}s, "
              f"median={sorted(per_paper_latency)[len(per_paper_latency)//2] if per_paper_latency else 0:.1f}s, "
              f"max={max(per_paper_latency) if per_paper_latency else 0:.1f}s")
        print(f"\nOutput: {final_summaries_path}")
        if delta_path:
            print(f"Delta: {delta_path}")
        print("=" * 80)

    except Exception as e:
        LOG.exception(f"Processor error: {e}")
        # Attempt to close writer and save partial stats for resumability
        try:
            try:
                final_summaries_path = storage.close_summaries_writer()
            except Exception:
                tmp_path, final_path = storage.get_current_writer_paths()
                final_summaries_path = (final_path or tmp_path or storage.paths.summaries_dir)
            elapsed = time.time() - start
            partial_stats = {
                "run_id": run_id,
                "mode": args.mode,
                "papers_in": papers_in,
                "papers_out": papers_out,
                "skipped_empty": skipped_empty,
                "skipped_dedup": skipped_dedup,
                "store_fulltext_used": store_fulltext_used,
                "store_abstract_used": store_abstract_used,
                "failed_count": len(failed_papers),
                "slow_count": len(slow_papers),
                "chunks_total": chunks_total,
                "elapsed_sec": elapsed,
                "summaries_path": str(final_summaries_path.as_posix()) if hasattr(final_summaries_path, 'as_posix') else str(final_summaries_path),
                "error": str(e),
            }
            storage.save_processing_stats(partial_stats)
        except Exception:
            pass

if __name__ == "__main__":
    main()


