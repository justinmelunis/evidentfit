# Agent A: Ingest Pipeline

## Overview

**Agent A** ingests research papers from PubMed into EvidentFit's knowledge base. It consists of two sequential stages:

1. **get_papers** - Fast, LLM-free paper discovery, selection, and full-text fetching
2. **paper_processor** - GPU-accelerated LLM processing for structured summaries

## Quick Start

### Stage 1: Get Papers (30k papers, ~10 hours with API key)

```bash
# Recommended: Get NCBI API key first (https://www.ncbi.nlm.nih.gov/account/settings/)
export NCBI_API_KEY="your_key_here"
export NCBI_EMAIL="you@example.com"

python -m agents.ingest.get_papers.pipeline \
  --mode bootstrap \
  --target 30000 \
  --fulltext-concurrency 8
```

**What it does:**
- Multi-supplement PubMed search (63 supplements, ~190K candidates)
- Quality filtering (2.0+ threshold, never compromised, ~125K pass)
- Enhanced quota system: 10 best overall + 2 per goal per supplement (~715 protected)
- Diversity selection with 0.8 tiebreak threshold (prefer full-text when close)
- PMC + Unpaywall full-text fetching (85-90% coverage)
- Intelligent content extraction with quality detection
- Centralized sharded storage

**Output:**
- `data/ingest/runs/<timestamp>/pm_papers.jsonl` - 30k selected papers
- `data/ingest/runs/<timestamp>/metadata.json` - Run statistics
- `data/ingest/runs/<timestamp>/fulltext_manifest.json` - Full-text fetch summary  
- `data/fulltext_store/` - Centralized repository (25-27k full texts, ~900 MB)

### Stage 2: Paper Processor (GPU required, ~5 days on RTX 3080)

```bash
python -m agents.ingest.paper_processor.run \
  --max-papers 30000 \
  --batch-size 1 \
  --model mistralai/Mistral-7B-Instruct-v0.3
```

**What it does:**
- Streams papers from disk (low RAM)
- Smart chunking for long full-text papers
- Two-pass LLM extraction (initial + repair)
- Generates structured Q&A summaries
- Incremental output writing (resume-safe)

**Output:**
- `data/paper_processor/summaries/summaries_<timestamp>.jsonl` - Structured summaries
- `data/paper_processor/stats/stats_<timestamp>.json` - Processing statistics
- Comprehensive telemetry (coverage, chunks, latency, evidence grades)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: get_papers (LLM-free)                                  │
│                                                                  │
│  PubMed Multi-Query (63 supplements)                            │
│       ↓                                                          │
│  ~190K PMIDs fetched                                            │
│       ↓                                                          │
│  Parse XML & Score (rule-based)                                 │
│       ↓                                                          │
│  ~125K Human Studies (animal/vitro filtered)                    │
│       ↓                                                          │
│  Quality Filter (threshold: 2.0)                                │
│       ↓                                                          │
│  ~69K Quality Papers                                            │
│       ↓                                                          │
│  Diversity Selection (30k target, min quotas)                   │
│       ↓                                                          │
│  Save JSONL → data/ingest/runs/<timestamp>/pm_papers.jsonl      │
│       ↓                                                          │
│  PMC Full-Text Fetch (default ON, ~10 hrs with API key)        │
│       ↓                                                          │
│  PMC: ~22k full texts + ~6k abstract-only                       │
│       ↓                                                          │
│  Unpaywall Rescue (for PMC abstract-only papers)                │
│       ↓                                                          │
│  Unpaywall: +3-5k full texts (rescue from PMC abstract-only)    │
│       ↓                                                          │
│  Centralized Store → data/fulltext_store/ (25-27k full texts)   │
│  Abstracts retained for remaining ~3-5k papers (final fallback) │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2: paper_processor (GPU + Mistral-7B, ~5 days RTX 3080)  │
│                                                                  │
│  Stream pm_papers.jsonl (full text where available, else abstract)│
│       ↓                                                          │
│  Smart Chunking (long full texts → safe chunks)                 │
│       ↓                                                          │
│  Two-Pass Mistral-7B (strict prompt + repair)                   │
│       ↓                                                          │
│  Merge Chunks → Doc-level Summary                               │
│       ↓                                                          │
│  Stream Write → data/paper_processor/summaries/                 │
│       ↓                                                          │
│  28-29k Structured Q&A Summaries (resume-safe)                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### [get_papers](get_papers/) 
Fast paper discovery, selection, and full-text fetching.

- **No LLM**: Rule-based for speed and zero cost
- **Multi-query**: 63 supplement-specific searches (~190K candidates)
- **Quality scoring**: Meta-analyses, RCTs, sample size, journal impact
- **Diversity filtering**: Iterative selection with minimum quotas
- **Full-text fetching**: PMC + Unpaywall integration (85-90% combined coverage)
- **Enhanced quotas**: 10 best overall + 2 per goal per supplement (~715 protected)
- **Smart selection**: 0.8 tiebreak threshold prefers full-text without quality compromise
- **Hybrid content**: Full text for 25-27k papers, abstracts for remaining 3-5k
- **Centralized storage**: Sharded, deduplicated, resume-safe
- **Performance**: ~10 hours with NCBI API key, ~30 hours without
- **Output**: 30k selected papers (25-27k full texts + 3-5k abstracts, ~900 MB total)

📖 **[Detailed Documentation](get_papers/README.md)**

### [paper_processor](paper_processor/)
GPU-accelerated structured analysis with Mistral-7B.

- **Model**: Mistral-7B-Instruct-v0.3 (4-bit quantization, Flash Attention 2)
- **Hardware**: RTX 3080 recommended (10GB VRAM, uses 6-8GB)
- **Architecture**: Streaming I/O, smart chunking, two-pass extraction
- **Resume capability**: Pick up where you left off after interruptions
- **Performance**: ~5 days for 30K papers, 4-5 papers/minute
- **Quality**: Two-pass extraction (initial + repair) ensures complete summaries
- **Output**: Structured Q&A summaries with evidence grades and key findings
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
- Enhanced quotas: 10 best overall + 2 per goal per supplement (~715 protected total)
- Iterative filtering with 0.8 tiebreak threshold (prefer full-text when close)
- Full-text preference never compromises quality (tiebreaker only)
- Prevents corpus domination by popular supplements

### Hybrid Content Strategy (Full Text + Abstracts)
- **Dual-source fetching**: PMC (primary) + Unpaywall (rescue)
- **PMC coverage**: ~73% true full-text, ~20% abstract-only (93% total PMC response)
- **Unpaywall rescue**: Attempts to fetch full PDF for PMC abstract-only papers
- **Expected rescue rate**: 50-70% of PMC abstract-only → +12-17% overall coverage
- **Combined coverage**: 85-90% full-text (25,000-27,000 of 30k papers)
- **Final fallback**: PubMed abstracts for remaining 10-15% (always available)
- **Quality detection**: Distinguishes true full-text (with body) from abstract-only
- **Clean extraction**: Title, abstract, body, tables, figures from both XML and PDF
- **Centralized storage**: Sharded, deduplicated repository (~900 MB total)
- **Resume-safe**: Automatic deduplication and skip of existing files

### Performance
| Stage | Papers | Runtime (with API key) | Storage |
|-------|--------|----------------------|---------|
| get_papers | 30,000 | ~10 hours | ~900 MB |
| paper_processor | 30,000 | ~5 days (RTX 3080) | ~500 MB |

**Note**: Paper processor is GPU-bound; runtime depends on hardware. RTX 3080 processes ~4-5 papers/minute.

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
