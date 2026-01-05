"""
Index Papers CLI (Module 2): chunk -> embed -> vector DB

Subcommands:
  prep         : run join+chunk using index_prep (Module 2 shim)
  load-chunks  : load chunks.jsonl(.gz) into Postgres (ef_chunks)
  embed        : batch-embed missing chunks into ef_chunk_embeddings
  search       : quick top-K cosine search in Postgres

Usage:
  python -m agents.ingest.index_papers.cli prep --chunks-mode text
  python -m agents.ingest.index_papers.cli load-chunks
  python -m agents.ingest.index_papers.cli embed
  python -m agents.ingest.index_papers.cli search --q "creatine 1RM"
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
 

def cmd_prep(args):
    if args.chunks_mode:
        os.environ["CHUNKS_WRITE_MODE"] = args.chunks_mode
    # Import from Module 2 location (shim re-exports existing build_index)
    from agents.ingest.index_papers import index_prep
    start = time.time()
    try:
        if args.store_dir:
            res = index_prep.build_index(store_dir=Path(args.store_dir))
        else:
            res = index_prep.build_index()
    except TypeError:
        res = index_prep.build_index()
    elapsed = time.time() - start
    print(json.dumps(res, indent=2))
    print(f"elapsed_sec: {elapsed:0.1f}")
    print("outputs: data/index/{canonical_papers.jsonl, chunks.jsonl(.gz), schema.json}")

def cmd_load_chunks(args):
    from agents.ingest.index_papers.pgvector_cli import load_chunks
    load_chunks(args)

def cmd_embed(args):
    from agents.ingest.index_papers.pgvector_cli import embed
    embed(args)

def cmd_search(args):
    from agents.ingest.index_papers.pgvector_cli import search
    search(args)

def main():
    ap = argparse.ArgumentParser(prog="index_papers", description="Index Papers: chunk, embed, vector DB")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prep")
    p_prep.add_argument("--chunks-mode", choices=["text","refs"], default=None)
    p_prep.add_argument("--store-dir", type=str, default=None)

    p_load = sub.add_parser("load-chunks")
    p_load.add_argument("--chunks", default=None, help="Path to chunks.jsonl(.gz)")

    p_embed = sub.add_parser("embed")
    p_embed.add_argument("--limit", type=int, default=None)
    p_embed.add_argument("--model", type=str, default=None)

    p_search = sub.add_parser("search")
    p_search.add_argument("--q", type=str, required=True)
    p_search.add_argument("-k", type=int, default=10)
    # pass-through optional supplement filter to pgvector_cli.search
    p_search.add_argument("--supp", default=None, help="Optional supplement filter (e.g., creatine)")
    p_search.add_argument("--supp-mode", choices=["meta","text","both"], default="meta",
                          help="How to interpret --supp filter (default: meta)")
    p_search.add_argument("--results-first", action="store_true", help="Slightly boost Results-section chunks")

    # Optional: build-ann and analyze wrappers for pgvector CLI parity
    p_ann = sub.add_parser("build-ann")
    p_ann.add_argument("--lists", type=int, default=200)
    p_ann.add_argument("--recreate", action="store_true")

    sub.add_parser("analyze")

    args = ap.parse_args()
    if args.cmd == "prep":
        cmd_prep(args)
    elif args.cmd == "load-chunks":
        cmd_load_chunks(args)
    elif args.cmd == "embed":
        cmd_embed(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "build-ann":
        from agents.ingest.index_papers.pgvector_cli import build_ann
        build_ann(args)
    elif args.cmd == "analyze":
        from agents.ingest.index_papers.pgvector_cli import analyze
        analyze(args)

if __name__ == "__main__":
    main()

