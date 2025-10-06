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
import json
import time
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
    p = Path(papers_path)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    if not p.exists():
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
    ap.add_argument("--model", type=str, default="mistralai/Mistral-7B-Instruct-v0.3")
    ap.add_argument("--resume-summaries", type=str, default=None, help="Path to an existing summaries .jsonl or .jsonl.tmp to resume into")
    args = ap.parse_args()

    run_id = f"paper_processor_{int(time.time())}"
    setup_logging()
    LOG.info("=" * 80)
    LOG.info("PAPER PROCESSOR START (streaming + resume)")
    LOG.info("=" * 80)
    LOG.info(f"Run: {run_id}")

    papers_jsonl = resolve_selected_papers(args.papers_jsonl)
    LOG.info(f"Selected papers: {papers_jsonl}")

    cfg = ProcessingConfig(
        model_name=args.model,
        ctx_tokens=args.ctx_tokens,
        max_new_tokens=args.max_new_tokens,
        temperature=0.0,  # deterministic → stable outputs & slight perf benefit
        batch_size=args.batch_size,
        microbatch_size=args.microbatch_size,
        use_4bit=True,
        device_map="auto",
        enable_schema_validation=True,
        enable_model_repair=False,
        schema_version="v1.2",
    )
    client = MistralClient(cfg)

    storage = StorageManager()
    storage.initialize()

    # Resume: pre-load seen dedupe keys from existing summaries (tmp or final)
    seen_keys = set()
    if args.resume_summaries:
        resume_path = Path(args.resume_summaries)
        LOG.info(f"Resume requested from: {resume_path}")
        for dk in storage.iter_dedupe_keys(resume_path):
            seen_keys.add(dk)
        storage.open_summaries_writer(resume_path=str(resume_path))
    else:
        storage.open_summaries_writer()

    # Telemetry counters
    papers_in = 0
    papers_out = 0
    skipped_empty = 0
    skipped_dedup = 0
    chunks_total = 0
    per_paper_latency: List[float] = []
    
    # NEW: Enhanced tracking
    fulltext_used = 0
    abstract_only = 0
    failed_papers: List[Dict[str, Any]] = []
    slow_papers: List[Dict[str, Any]] = []

    # On-the-fly aggregate stats
    year_values: List[int] = []
    study_type_counts = Counter()
    evidence_grade_counts = Counter()
    supplement_counts = Counter()

    start = time.time()

    try:
        for idx, p in enumerate(stream_jsonl(papers_jsonl, limit=args.max_papers), 1):
            papers_in += 1
            t0 = time.time()

            content = p.get("content") or ""
            if not content or len(content) < 20:
                skipped_empty += 1
                continue

            dkey = create_dedupe_key(p)
            if dkey in seen_keys:
                skipped_dedup += 1
                continue
            seen_keys.add(dkey)
            
            # Track full-text vs abstract usage
            if p.get("fulltext_source") or p.get("has_fulltext"):
                fulltext_used += 1
            else:
                abstract_only += 1

            # Chunk
            chunks = _split_text_safely(content, args.ctx_tokens, args.max_new_tokens)
            if not chunks:
                skipped_empty += 1
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
            chunk_summaries = client.generate_batch_summaries(chunk_inputs)

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

            storage.write_summary_line(merged)
            papers_out += 1
            
            paper_elapsed = time.time() - t0
            per_paper_latency.append(paper_elapsed)

            # Update aggregates for stats
            y = merged.get("year")
            if isinstance(y, int):
                year_values.append(y)
            st = merged.get("study_type", "unknown")
            eg = merged.get("evidence_grade", "D")
            study_type_counts[st] += 1
            evidence_grade_counts[eg] += 1
            for s in (merged.get("supplements") or []):
                if s:
                    supplement_counts[s] += 1
            
            # Performance monitoring: Track slow papers
            if paper_elapsed > 60:  # >1 minute
                slow_papers.append({
                    "pmid": p.get("pmid"),
                    "title": p.get("title", "")[:100],
                    "elapsed_sec": round(paper_elapsed, 2),
                    "chunks": len(chunks),
                    "content_chars": len(content)
                })
                LOG.warning(f"Slow paper detected: {p.get('pmid')} took {paper_elapsed:.1f}s ({len(chunks)} chunks, {len(content):,} chars)")
            
            # Progress reporting: Every 100 papers
            if papers_out % 100 == 0:
                elapsed = time.time() - start
                rate = papers_out / elapsed if elapsed > 0 else 0
                remaining_papers = args.max_papers - papers_out
                eta_sec = remaining_papers / rate if rate > 0 else 0
                eta_hours = eta_sec / 3600
                progress_pct = (papers_out / args.max_papers * 100) if args.max_papers > 0 else 0
                
                LOG.info(f"PROGRESS: {papers_out}/{args.max_papers} papers ({progress_pct:.1f}%) | "
                        f"Rate: {rate*60:.1f} papers/min | "
                        f"ETA: {eta_hours:.1f}h | "
                        f"Full-text: {fulltext_used}/{papers_out} ({fulltext_used/papers_out*100:.1f}%)")

            if torch.cuda.is_available() and (idx % max(1, args.batch_size) == 0):
                torch.cuda.empty_cache()

        final_summaries_path = storage.close_summaries_writer()

        elapsed = time.time() - start
        stats = {
            "run_id": run_id,
            "papers_in": papers_in,
            "papers_out": papers_out,
            "skipped_empty": skipped_empty,
            "skipped_dedup": skipped_dedup,
            "coverage_ratio": (papers_out / papers_in) if papers_in else None,
            
            # Full-text validation
            "fulltext_used": fulltext_used,
            "abstract_only": abstract_only,
            "fulltext_ratio": (fulltext_used / papers_out) if papers_out > 0 else 0.0,
            
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
            
            # Index stats
            "index_stats": {
                "total_papers": papers_out,
                "study_types": dict(study_type_counts),
                "evidence_grades": dict(evidence_grade_counts),
                "year_range": {
                    "min": min(year_values) if year_values else None,
                    "max": max(year_values) if year_values else None,
                },
                "supplements": dict(supplement_counts),
            },
            "summaries_path": str(final_summaries_path.as_posix()),
        }
        storage.save_processing_stats(stats)
        LOG.info("Done.")
        
        # Enhanced final summary
        print("\n" + "=" * 80)
        print("PAPER PROCESSOR COMPLETE")
        print("=" * 80)
        print(f"Papers: {papers_out} successful / {papers_in} total ({papers_out/papers_in*100:.1f}%)")
        print(f"Skipped: {skipped_empty} empty, {skipped_dedup} duplicates")
        print(f"Failed: {len(failed_papers)} papers ({len(failed_papers)/papers_in*100:.1f}%)")
        print(f"\nFull-text: {fulltext_used}/{papers_out} ({fulltext_used/papers_out*100:.1f}%)")
        print(f"Abstract-only: {abstract_only}/{papers_out} ({abstract_only/papers_out*100:.1f}%)")
        print(f"\nChunking: {chunks_total} total chunks, avg {chunks_total/papers_out:.2f} per paper")
        print(f"Slow papers (>60s): {len(slow_papers)}/{papers_out} ({len(slow_papers)/papers_out*100:.1f}%)")
        print(f"\nTime: {elapsed/3600:.2f} hours ({papers_out/elapsed*60:.1f} papers/min)")
        print(f"Latency: min={min(per_paper_latency) if per_paper_latency else 0:.1f}s, "
              f"median={sorted(per_paper_latency)[len(per_paper_latency)//2] if per_paper_latency else 0:.1f}s, "
              f"max={max(per_paper_latency) if per_paper_latency else 0:.1f}s")
        print(f"\nOutput: {final_summaries_path}")
        print("=" * 80)

    except Exception as e:
        LOG.exception(f"Processor error: {e}")

if __name__ == "__main__":
    main()
