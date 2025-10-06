#!/usr/bin/env python3
"""
Paper processing pipeline.

- Loads selected papers (default: get_papers latest pointer → pm_papers.jsonl)
- Feeds paper content (from get_papers) into Mistral pipeline
- Saves structured summaries + search index + stats via StorageManager

Note: Full-text fetching is now handled by get_papers pipeline (default enabled).
"""

import argparse
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from evidentfit_shared.utils import PROJECT_ROOT
from logging_config import setup_logging
from storage_manager import StorageManager
from mistral_client import MistralClient, ProcessingConfig
from schema import (
    create_search_index,
    normalize_data,
    create_dedupe_key,
    validate_optimized_schema,
)

import torch

LOG = logging.getLogger(__name__)

# -------------------------
# Helpers
# -------------------------

def load_jsonl(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
  items: List[Dict[str, Any]] = []
  with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
      if line.strip():
        try:
          items.append(json.loads(line))
        except Exception:
          continue
      if limit and len(items) >= limit:
        break
  return items

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


# -------------------------
# Main
# -------------------------

def main():
  ap = argparse.ArgumentParser(description="EvidentFit paper processor")
  ap.add_argument("--papers-jsonl", type=str, help="Path to pm_papers.jsonl (optional; defaults to runs/latest.json pointer)")
  ap.add_argument("--max-papers", type=int, default=200, help="Max papers to process")
  ap.add_argument("--batch-size", type=int, default=2)
  ap.add_argument("--microbatch-size", type=int, default=1)
  ap.add_argument("--ctx-tokens", type=int, default=16384)
  ap.add_argument("--max-new-tokens", type=int, default=640)
  ap.add_argument("--model", type=str, default="mistralai/Mistral-7B-Instruct-v0.3")

  args = ap.parse_args()

  run_id = f"paper_processor_{int(time.time())}"
  setup_logging()
  LOG.info("=" * 80)
  LOG.info("PAPER PROCESSOR START")
  LOG.info("=" * 80)
  LOG.info(f"Run: {run_id}")

  # Resolve input list
  papers_jsonl = resolve_selected_papers(args.papers_jsonl)
  LOG.info(f"Selected papers: {papers_jsonl}")

  # Load selected papers (content already populated by get_papers)
  papers = load_jsonl(papers_jsonl, limit=args.max_papers)
  LOG.info(f"Loaded {len(papers)} papers to process")

  # Configure Mistral
  cfg = ProcessingConfig(
    model_name=args.model,
    ctx_tokens=args.ctx_tokens,
    max_new_tokens=args.max_new_tokens,
    temperature=0.2,
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
  all_summaries: List[Dict[str, Any]] = []
  start = time.time()

  try:
    # Process in batches
    bs = max(1, args.batch_size)
    total = len(papers)
    for i in range(0, total, bs):
      batch = papers[i:i+bs]
      LOG.info(f"Batch {i//bs + 1}/{(total + bs - 1)//bs}: {len(batch)} papers")
      # The client builds prompts internally from each paper's content/title/etc.
      summaries = client.generate_batch_summaries(batch)
      if not summaries:
        LOG.warning("Empty summaries for batch")
        continue
      # Normalize / dedupe key / (client may already validate)
      for s in summaries:
        try:
          s = normalize_data(s)
          s["dedupe_key"] = create_dedupe_key(s)
          if not validate_optimized_schema(s):
            LOG.debug("Schema validation failed (will still store for later repair)")
          all_summaries.append(s)
        except Exception:
          continue
      # Release GPU cache each step
      if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Build index + save artifacts
    if all_summaries:
      LOG.info("Creating search index…")
      search_index = create_search_index(all_summaries)
      LOG.info("Saving structured summaries…")
      storage.save_structured_summaries(all_summaries)
      LOG.info("Saving processing stats…")
      elapsed = time.time() - start
      stats = {
        "run_id": run_id,
        "papers_in": total,
        "papers_out": len(all_summaries),
        "elapsed_sec": elapsed,
        "rate_papers_per_sec": (len(all_summaries) / elapsed) if elapsed > 0 else None,
        "model": args.model,
        "ctx_tokens": args.ctx_tokens,
        "max_new_tokens": args.max_new_tokens,
        "index_stats": search_index.get("statistics", {})
      }
      storage.save_processing_stats(stats)
      LOG.info("Done.")
      print(f"\nProcessed {len(all_summaries)} papers in {elapsed:.2f}s")
      if all_summaries:
        s = all_summaries[0]
        print(f"Sample → {s.get('title','')[:80]}… | grade={s.get('evidence_grade')} | q={s.get('quality_score')}")
    else:
      LOG.warning("No summaries generated")

  except Exception as e:
    LOG.exception(f"Processor error: {e}")

if __name__ == "__main__":
  main()
