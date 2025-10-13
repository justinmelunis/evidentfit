# Index Papers (Module 2) — Chunking, Embeddings, and Vector DB

This module converts selected papers into search-ready chunks and embeddings, and optionally loads them into Postgres (pgvector).

## Outputs

- `data/index/canonical_papers.jsonl` — one row per paper with merged metadata
- `data/index/chunks.jsonl` — chunked text with normalized section info and metadata
- `data/index/schema.json` — schema reference for both files

## Key Features

- Full-text preferred, abstract fallback
- Section-aware chunking with overlap
- Deterministic chunk IDs and in-run deduplication
- Atomic file writes with Windows-safe replace
- Optional pgvector pipeline for local retrieval

## Quick Start

```bash
# 1) Build index files (join + chunk)
python -m agents.ingest.index_papers.cli prep --chunks-mode text

# 2) (Optional) Load chunks and embed into Postgres (pgvector)
psql "$DATABASE_URL" -f db/ddl/10_pgvector_setup.sql
python -m agents.ingest.index_papers.cli load-chunks
export EMBEDDING_MODEL=intfloat/e5-base-v2
python -m agents.ingest.index_papers.cli embed

# 3) Try a search
python -m agents.ingest.index_papers.cli search --q "creatine increases 1RM strength" -k 10
```

## Chunker (direct) — single-path CLI

Use the chunker directly when you already have `fulltext_store` JSONs and want fast, section-aware chunks.

```bash
# Directory input (auto-detects dir vs file); writes default report alongside chunks
python agents/ingest/index_papers/index_prep.py data/fulltext_store --out data/index/chunks.jsonl
# => also writes data/index/chunks.jsonl.report.jsonl

# Single file input (ad-hoc debug)
python agents/ingest/index_papers/index_prep.py data/fulltext_store/00/1e/pmid_18590587.json --out data/index/chunks_one.jsonl
# => also writes data/index/chunks_one.jsonl.report.jsonl

# Optional: custom report path and limit when using a directory
python agents/ingest/index_papers/index_prep.py data/fulltext_store --out data/index/chunks.jsonl --report data/index/report.jsonl --max 500

# Optional: update canonical metadata with relabels (narrative review, banking eligibility)
python agents/ingest/index_papers/index_prep.py data/fulltext_store --out data/index/chunks.jsonl --update-canonical --canonical-path data/index/canonical_papers.jsonl
```

Notes:
- The chunker auto-detects file vs directory.
- Report JSONL defaults to `<out>.report.jsonl` if `--report` is omitted.
- Multiprocessing workers are chosen automatically; no `--workers` flag.
- The chunker uses a fast header detector with bounded structured-abstract handling to extract `introduction`, `methods`, `results`, and `discussion` where present.

## Chunk Schema (excerpt)

Each chunk row in `data/index/chunks.jsonl`:

```json
{
  "chunk_id": "pmid_12345678#abcd0123ef456789",
  "paper_id": "pmid_12345678",
  "pmid": "12345678",
  "doi": "10.1234/example",
  "section": "Methods:",
  "section_norm": "methods",
  "section_priority": 3,
  "is_results": false,
  "is_methods": true,
  "passage_id": "methods_0",
  "start": 1024,
  "end": 3320,
  "title": "Study Title",
  "journal": "Journal Name",
  "year": 2024,
  "study_type": "randomized_controlled_trial",
  "primary_goal": "strength",
  "supplements": ["creatine", "protein"],
  "reliability_score": 4.2,
  "text": "...chunk text..."
}
```

## Implementation Notes

- Builds a one-time in-memory index of `data/fulltext_store` keyed by PMID and DOI for O(1) lookups.
- Section normalization maps arbitrary headings to a stable set: `abstract`, `intro`, `methods`, `results`, `discussion`, `conclusion`, `other`. Helpers also derive flags like `is_results`/`is_methods` for downstream ranking.
- Chunking uses sliding windows with overlap within each section to preserve coherence (configurable size/overlap) and emits `passage_id` per section.
- Chunk IDs are deterministic SHA1 hashes over `(paper_id, section_norm, passage_idx, start_offset, end_offset, text_prefix)`; in-run dedup skips accidental duplicates.
- Writes to `.tmp` files then atomically replaces final paths using a Windows-hardened replace.

Why this design
- In-memory fulltext index: avoids repeated directory scans across ~30K JSON files; dramatically reduces I/O.
- Section normalization: makes ranking and UI logic predictable across heterogeneous publisher headings.
- Overlapping chunks: increases recall by reducing boundary misses; overlap balances recall vs index size.
- Deterministic IDs: stable references across re-runs; safe upserts to Postgres.
- Atomic writes: prevents partial files on Windows; safe to resume after interruptions.

## Embeddings and pgvector

- Default embedding model: `intfloat/e5-base-v2` (768d). Good recall for Q&A over chunks.
- Alternatives:
  - Higher recall: `intfloat/e5-large-v2` (1024d)
  - Smaller/faster: `BAAI/bge-small-en-v1.5` (384d)
  - To align with cloud API embeddings later: `text-embedding-3-small` (1536d)

CLI commands:

```bash
# Initialize db objects (extension + tables only)
psql "$DATABASE_URL" -f db/ddl/10_pgvector_setup.sql

# Load chunks into ef_chunks (upsert)
python -m agents.ingest.index_papers.cli load-chunks

# Embed missing chunks into ef_chunk_embeddings
export EMBEDDING_MODEL=intfloat/e5-base-v2
python -m agents.ingest.index_papers.cli embed

# Search
python -m agents.ingest.index_papers.cli search --q "beta-alanine endurance" -k 10 --results-first
python -m agents.ingest.index_papers.cli search --q "creatine increases 1RM strength" --supp creatine --supp-mode both -k 10

Search details:
- Uses e5 query prefix (`query: ...`) to improve relevance.
- Optional `--supp` filter with `--supp-mode meta|text|both` applies:
  - metadata match: checks `supplements` array for exact/LIKE
  - text match: FTS over `title` and, with a guard, over body text for `results`/`abstract` sections
- Optional `--results-first` applies a small bonus when section starts with `results`.

Why these choices
- E5 models respond well to the `query:` prefix; improves alignment with retrieval tasks.
- Hybrid scoring (vector + tiny textual bonuses) keeps vector search primary while nudging obviously relevant chunks.
- Guarded body FTS (results/abstract) reduces noise from methods-heavy sections when doing text filters.
```

## Configuration

Environment variables:

```bash
# Embeddings
export EMBEDDING_MODEL=intfloat/e5-base-v2
export BATCH_SIZE=64

# Database
export DATABASE_URL=postgres://user:pass@host:5432/db
```

## Troubleshooting

- `chunks.jsonl` empty: ensure `pm_papers.jsonl` exists and `data/ingest/runs/latest.json` points to it; check `fulltext_store` presence.
- Vector dim mismatch: the CLI auto-resizes `vector(dim)` to match your model on first run.
- Psycopg2 adaptation error: embeddings coerced to native Python floats in `_embed_batch`.
