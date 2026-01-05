## get_papers — Definition of Done

This folder is considered **finalized** when:

1. `data/ingest/runs/latest.json` exists and includes:
   - `papers_path`, `fulltext_store_dir` (and optionally `fulltext_manifest`)
2. `python -m agents.ingest.get_papers.validate_schema` returns `"invalid_rows": 0`
3. `python -m agents.ingest.get_papers.coverage_report` prints coverage with a sensible `pct_fulltext`
4. `python -m agents.ingest.get_papers.finalize_get_papers` writes `data/ingest/runs/DONE_SUMMARY.json` with `"status": "ready"`

**Contracts for downstream steps**
- `pm_papers.jsonl` rows contain required keys (empty allowed)
- Full-text store JSONs keep `fulltext_text` only when body sections exist
- Downstream indexers should *only* read `data/ingest/runs/latest.json` for paths

**Next**: run the indexer (join + chunk) then build embeddings & retrieval index.


