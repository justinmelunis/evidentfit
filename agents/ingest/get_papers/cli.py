"""
Minimal CLI for the get_papers lane — one file, three commands:
  validate   : check pm_papers.jsonl has required keys
  coverage   : compute fulltext vs abstract coverage
  finalize   : write DONE_SUMMARY.json (status + reports)

Usage examples:
  python -m agents.ingest.get_papers.cli validate
  python -m agents.ingest.get_papers.cli coverage
  python -m agents.ingest.get_papers.cli finalize
  # (index prep has moved to Module 2: agents.ingest.index_papers.cli)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------- Shared helpers ----------
LATEST = Path("data/ingest/runs/latest.json")
DONE_PATH = Path("data/ingest/runs/DONE_SUMMARY.json")
REQUIRED_KEYS = [
    "pmid","doi","title","journal","year",
    "study_type","study_category","primary_goal",
    "supplements","outcomes","population",
    "sample_size","study_duration","dosage_info",
    "has_loading_phase","has_maintenance_phase",
    "safety_indicators","has_side_effects","has_contraindications",
    "reliability_score","study_design_score","content"
]

def _read_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def _iter_jsonl(p: Path) -> Iterable[Dict[str, Any]]:
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                raise RuntimeError(f"Invalid JSON on line {i} of {p}: {e}") from e

# ---------- Commands ----------
def cmd_validate(args) -> Dict[str, Any]:
    if not LATEST.exists():
        raise SystemExit("latest.json not found at data/ingest/runs/latest.json")
    ptr = _read_json(LATEST)
    papers_path = Path(ptr["papers_path"])
    total = 0
    ok = 0
    problems: List[Tuple[str, List[str]]] = []
    for row in _iter_jsonl(papers_path):
        total += 1
        missing = [k for k in REQUIRED_KEYS if k not in row]
        if missing:
            problems.append((row.get("pmid") or row.get("doi") or f"row#{total}", missing))
        else:
            ok += 1
    output = {
        "papers_path": str(papers_path),
        "total_rows": total,
        "valid_rows": ok,
        "invalid_rows": len(problems),
        "examples": problems[:20],
    }
    print(json.dumps(output, indent=2))
    return output

def cmd_coverage(args) -> Dict[str, Any]:
    if not LATEST.exists():
        raise SystemExit("latest.json not found at data/ingest/runs/latest.json")
    ptr = _read_json(LATEST)
    manifest_path = Path(ptr.get("fulltext_manifest") or "")
    if manifest_path.exists():
        man = _read_json(manifest_path)
        # Support multiple historical key names
        total = int(man.get("papers_in_store") or man.get("total") or 0)
        # full text variants seen in different manifest versions
        full_variants = [
            "full_text_with_body",  # preferred in current fetcher
            "full_text_total",      # sometimes used in summaries
            "fulltext_with_body",   # older CLI expectation
            "fulltext_count"        # very old variant
        ]
        full = 0
        for k in full_variants:
            if k in man and isinstance(man[k], (int, float)):
                full = int(man[k])
                break
        # abstract-only (if present) or derive
        abstract_only = man.get("abstract_only_final")
        if abstract_only is None and total and full:
            abstract_only = max(total - full, 0)
        abstract_only = int(abstract_only or 0)
        out = {
            "manifest_path": str(manifest_path),
            "store_dir": str(ptr["fulltext_store_dir"]),
            "papers_in_store": total,
            "fulltext_with_body": full,
            "abstract_only_final": abstract_only,
            "pct_fulltext": (100.0 * full / total) if total else 0.0,
        }
        print(json.dumps(out, indent=2))
        return out
    # fallback: scan store
    store_dir = Path(ptr["fulltext_store_dir"])
    total = 0
    full = 0
    for shard1 in store_dir.glob("*"):
        if not shard1.is_dir(): continue
        for shard2 in shard1.glob("*"):
            if not shard2.is_dir(): continue
            for rec in shard2.glob("*.json"):
                total += 1
                try:
                    recd = _read_json(rec)
                except Exception:
                    continue
                sources = recd.get("sources", {})
                pmc_has = bool(sources.get("pmc", {}).get("has_body_sections"))
                upw_has = bool(sources.get("unpaywall", {}).get("has_body_sections"))
                fulltext = (recd.get("fulltext_text") or "").strip()
                if fulltext and (pmc_has or upw_has):
                    full += 1
    out = {
        "manifest_path": None,
        "store_dir": str(store_dir),
        "papers_in_store": total,
        "fulltext_with_body": full,
        "abstract_only_final": total - full,
        "pct_fulltext": (100.0 * full / total) if total else 0.0,
    }
    print(json.dumps(out, indent=2))
    return out

def cmd_finalize(args) -> Dict[str, Any]:
    schema = cmd_validate(args)
    coverage = cmd_coverage(args)
    status = "ready" if schema["invalid_rows"] == 0 else "needs_fix"
    out = {
        "status": status,
        "schema": schema,
        "coverage": coverage,
        "next_steps": [
            "Run index prep (join + chunk) to create data/index/canonical_papers.jsonl and chunks.jsonl",
            "Then run embeddings + local retrieval index (pgvector/FAISS/Lance)"
        ]
    }
    DONE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DONE_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return out

def main():
    ap = argparse.ArgumentParser(prog="get_papers.cli", description="Minimal CLI for get_papers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate")
    sub.add_parser("coverage")
    sub.add_parser("finalize")

    args = ap.parse_args()
    if args.cmd == "validate":
        cmd_validate(args)
    elif args.cmd == "coverage":
        cmd_coverage(args)
    elif args.cmd == "finalize":
        cmd_finalize(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()

