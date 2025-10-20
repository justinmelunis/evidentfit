# Paper Processor (Agent B)

Moved from `agents/ingest/paper_processor/` to `agents/paper_processor/`.

Usage examples mirror the previous paths, e.g.:

- python -m agents.paper_processor.run --max-papers 2000
- python -m agents.paper_processor.cli collect --canonical data/index/canonical_papers.jsonl --chunks data/index/chunks.jsonl --outdir data/cards/_raw
- python -m agents.paper_processor.cli extract --bundle data/cards/_raw/33562750.json --outdir data/cards

Prompts are under `agents/paper_processor/prompts/`.
