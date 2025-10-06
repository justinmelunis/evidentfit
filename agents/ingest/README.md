# Agent A: Ingest Pipeline

## Overview

**Agent A** ingests research papers from PubMed into EvidentFit's knowledge base. It consists of two sequential stages:

1. **get_papers** - Fast, LLM-free paper discovery, selection, and full-text fetching
2. **paper_processor** - GPU-accelerated LLM processing for structured summaries

## Quick Start

### Stage 1: Get Papers (30k papers, ~30 hours with API key)

```bash
# Recommended: Get NCBI API key first (https://www.ncbi.nlm.nih.gov/account/settings/)
export NCBI_API_KEY="your_key_here"

python -m agents.ingest.get_papers.pipeline \
  --mode bootstrap \
  --target 30000 \
  --fetch-fulltext \
  --fulltext-concurrency 2
```

**Output:**
- `data/ingest/runs/<timestamp>/pm_papers.jsonl` - 30k selected papers
- `data/ingest/runs/<timestamp>/metadata.json` - Run statistics
- `data/ingest/runs/<timestamp>/fulltext_manifest.json` - PMC fetch summary
- `data/fulltext_store/` - Centralized full-text repository (~900 MB)

### Stage 2: Paper Processor (GPU required)

```bash
python -m agents.ingest.paper_processor.run \
  --max-papers 30000 \
  --batch-size 2 \
  --model mistralai/Mistral-7B-Instruct-v0.3
```

**Output:**
- `data/paper_processor/summaries/summaries_<timestamp>.jsonl` - Structured summaries
- `data/paper_processor/stats/stats_<timestamp>.json` - Processing statistics

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: get_papers (LLM-free)                                  │
│                                                                  │
│  PubMed Multi-Query (63 supplements)                            │
│       ↓                                                          │
│  Parse & Score (rule-based)                                     │
│       ↓                                                          │
│  Quality Filter (threshold: 2.0)                                │
│       ↓                                                          │
│  Diversity Selection (30k target)                               │
│       ↓                                                          │
│  Save JSONL → data/ingest/runs/<timestamp>/pm_papers.jsonl      │
│       ↓                                                          │
│  PMC Full-Text Fetch (default ON)                               │
│       ↓                                                          │
│  Centralized Store → data/fulltext_store/                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2: paper_processor (GPU + LLM)                            │
│                                                                  │
│  Load pm_papers.jsonl + full texts                              │
│       ↓                                                          │
│  Mistral-7B Processing (batch)                                  │
│       ↓                                                          │
│  Structured Summaries (Q&A schema)                              │
│       ↓                                                          │
│  Save → data/paper_processor/                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### [get_papers](get_papers/) 
Fast paper discovery and selection pipeline.

- **No LLM**: Rule-based for speed and cost
- **Multi-query**: 63 supplement-specific searches
- **Quality scoring**: Meta-analyses, RCTs, sample size, journal
- **Diversity filtering**: Balanced representation
- **Full-text fetching**: PMC integration (30-40% coverage)
- **Output**: 30k selected papers + full texts

📖 **[Detailed Documentation](get_papers/README.md)**

### [paper_processor](paper_processor/)
GPU-accelerated LLM processing for structured summaries.

- **Model**: Mistral-7B-Instruct (4-bit quantization)
- **Hardware**: RTX 3080 recommended (10GB VRAM)
- **Input**: JSONL from get_papers
- **Output**: Structured Q&A summaries
- **Schema**: Title, methods, findings, dosing, safety, evidence grade

📖 **[Detailed Documentation](paper_processor/README.md)**

## Key Features

### Quality-First Selection
- Prioritizes meta-analyses (12 pts) > RCTs (10 pts) > other study types
- Sample size scoring (up to 5 pts)
- Quality indicators: double-blind, placebo-controlled, etc.
- Minimum threshold: 2.0 (balanced selectivity)

### Diversity Optimization
- Balanced across supplements, goals, populations
- Iterative filtering with protected minimum quotas (3 per supplement)
- Prevents corpus domination by popular supplements

### Full-Text Fetching (Default ON)
- PMC integration via NCBI E-utilities
- ~30-40% coverage (9,000-12,000 of 30k papers)
- Clean extraction: title, abstract, body, tables, figures
- Centralized sharded storage (~900 MB total)
- Resume-safe with automatic deduplication

### Performance
| Stage | Papers | Runtime (with API key) | Storage |
|-------|--------|----------------------|---------|
| get_papers | 30,000 | ~10 hours | ~900 MB |
| paper_processor | 30,000 | ~3-6 hours | ~500 MB |

## Environment Setup

### Required
```bash
export NCBI_EMAIL="you@example.com"
export NCBI_API_KEY="your_key"  # Get from https://www.ncbi.nlm.nih.gov/account/
```

### Optional
```bash
export INGEST_LIMIT=30000
export QUALITY_FLOOR_BOOTSTRAP=2.0
export FULLTEXT_STORE_DIR="data/fulltext_store"
```

## Outputs

### Stage 1 (get_papers)
```
data/ingest/runs/<timestamp>/
├── pm_papers.jsonl              # Selected papers (30k)
├── metadata.json                # Statistics
├── protected_quota_report.json  # Minimum quota tracking
└── fulltext_manifest.json       # PMC fetch summary

data/fulltext_store/             # Centralized (shared across runs)
└── <shard>/<shard>/pmid_*.json  # Full texts (~30 KB each)
```

### Stage 2 (paper_processor)
```
data/paper_processor/
├── summaries/summaries_<timestamp>.jsonl
├── stats/stats_<timestamp>.json
└── latest.json
```

## Common Tasks

### Initial Bootstrap
```bash
# Get 30k papers with full text
python -m agents.ingest.get_papers.pipeline --mode bootstrap

# Process with GPU
python -m agents.ingest.paper_processor.run --max-papers 30000
```

### Monthly Updates
```bash
# Get new papers since last run
python -m agents.ingest.get_papers.pipeline --mode monthly

# Process updates
python -m agents.ingest.paper_processor.run
```

### Skip Full-Text Fetching
```bash
python -m agents.ingest.get_papers.pipeline --no-fetch-fulltext
```

## Troubleshooting

### 429 Rate Limit Errors
- **Solution**: Get NCBI API key or reduce `--fulltext-concurrency`
- System auto-retries with exponential backoff (1s, 5s, 15s)

### Low PMC Coverage
- **Expected**: Only 30-40% of papers are in PMC
- **Fallback**: Abstracts available for all papers

### Out of Memory (GPU)
- Reduce `--batch-size` in paper_processor
- Enable 4-bit quantization (default)

## More Information

- **[get_papers Details](get_papers/README.md)** - Scoring, diversity, full-text fetching
- **[paper_processor Details](paper_processor/README.md)** - GPU setup, Mistral configuration
- **[Project Root README](../../README.md)** - Overall EvidentFit architecture
