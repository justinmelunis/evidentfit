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
from logging_config import setup_logging
from storage_manager import StorageManager
from mistral_client import MistralClient, ProcessingConfig
from schema import (
    normalize_data,
    create_dedupe_key,
    validate_optimized_schema,
)
from evidentfit_shared.fulltext_store import load_by_pmid, resolve_fulltext_root

import torch

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
        # Prefer paragraph boundary, then sentence boundary
        k = text.rfind("\n\n", i, j)
        if k == -1:
            k = text.rfind(". ", i, j)
        if k == -1 or k <= i + 200:
            k = j
        chunk = text[i:k].strip()
        if chunk:
            chunks.append(chunk)
        i = k
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
    ap.add_argument("--preflight-only", action="store_true", help="Validate store coverage for selected papers and exit (no model load)")
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
    # Log fulltext store resolution for clarity
    try:
        store_root_path = resolve_fulltext_root()
        LOG.info(f"Fulltext store root: {store_root_path}")
    except Exception as e:
        LOG.warning(f"Could not resolve fulltext store root: {e}")

    # Optional preflight validation before expensive model load
    if args.preflight_only:
        LOG.info("Running preflight-only validation against fulltext store...")
        total = 0
        store_full = 0
        store_abs = 0
        store_missing_local = 0
        store_no_text_local = 0
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            total += 1
            pmid_val = p.get("pmid")
            sd = None
            try:
                if pmid_val:
                    sd = load_by_pmid(str(pmid_val))
            except Exception:
                sd = None
            if not sd:
                store_missing_local += 1
                continue
            ft = (sd.get("fulltext_text") or "").strip()
            ab = (sd.get("abstract") or "").strip()
            if ft:
                store_full += 1
            elif ab:
                store_abs += 1
            else:
                store_no_text_local += 1
        LOG.info(f"Preflight: total={total}, store_fulltext={store_full}, store_abstract={store_abs}, store_missing={store_missing_local}, store_no_text={store_no_text_local}")
        print(f"Preflight complete. total={total}, fulltext={store_full}, abstract={store_abs}, missing={store_missing_local}, no_text={store_no_text_local}")
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

    cfg = ProcessingConfig(
        model_name=args.model,
        ctx_tokens=args.ctx_tokens,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,  # 0.0 = deterministic; >0 enables sampling
        batch_size=args.batch_size,
        microbatch_size=args.microbatch_size,
        use_4bit=True,
        device_map="auto",
        seed=args.seed,
        enable_schema_validation=True,
        enable_model_repair=False,
        schema_version="v1.2",
    )
    client = MistralClient(cfg)

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

            # Store-only selection: PMID -> store doc; use fulltext_text else abstract
            pmid_val = p.get("pmid")
            store_doc = None
            try:
                if pmid_val:
                    store_doc = load_by_pmid(str(pmid_val))
            except Exception:
                store_doc = None
            if not store_doc:
                store_missing += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning(f"Store doc missing for PMID {pmid_val}")
                continue

            fulltext_text = (store_doc.get("fulltext_text") or "").strip()
            abstract_text = (store_doc.get("abstract") or "").strip()
            if abstract_text and len(abstract_text) > args.max_abstract_chars:
                abstract_text = abstract_text[:args.max_abstract_chars]

            content_source = None  # "fulltext" | "abstract"
            if fulltext_text:
                content = fulltext_text
                content_source = "fulltext"
                store_fulltext_used += 1
            elif abstract_text:
                content = abstract_text
                content_source = "abstract"
                store_abstract_used += 1
            else:
                store_no_text += 1
                skipped_empty += 1
                skipped_no_text += 1
                LOG.warning(f"Store has no fulltext or abstract for PMID {pmid_val}")
                continue
            if len(content) < 20:
                # Attempt abstract fallback if initial was fulltext
                if content_source == "fulltext" and abstract_text and len(abstract_text) >= 20:
                    content = abstract_text
                    content_source = "abstract"
                else:
                    skipped_empty += 1
                    skipped_too_short += 1
                    continue

            dkey = create_dedupe_key(p)
            if dkey in seen_keys:
                # If monthly mode and we have new fulltext while master had abstract-only, capture upgrade
                if args.mode == "monthly":
                    prior_src = (master_input_source.get(dkey) if 'master_input_source' in locals() else None) or "unknown"
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

            # Inference (effective batch ~1 to cap VRAM)
            try:
                chunk_summaries = client.generate_batch_summaries(chunk_inputs)
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
                        chunk_summaries = client.generate_batch_summaries(chunk_inputs)
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
                chunk_summaries = client.generate_batch_summaries(chunk_inputs)
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
