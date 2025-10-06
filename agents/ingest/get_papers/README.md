# get_papers - Paper Discovery & Selection Pipeline

## Overview

Fast, LLM-free pipeline that selects high-quality research papers from PubMed with balanced diversity across supplements, study types, and training goals. Features dual-source full-text fetching (PMC + Unpaywall) with intelligent quality-preserving selection.

## Features

- **No LLM calls**: Pure rule-based processing (fast, zero cost)
- **Multi-query search**: 63 supplement-specific PubMed queries (~190K candidates)
- **Quality scoring**: Meta-analyses, RCTs, sample size, journal impact (strict 2.0+ threshold)
- **Enhanced quotas**: 10 best overall + 2 per goal per supplement (~715 protected)
- **Smart diversity**: 0.8 tiebreak threshold prefers full-text without quality compromise
- **Dual-source fetching**: PMC + Unpaywall for 85-90% full-text coverage
- **Quality detection**: Distinguishes true full-text from abstract-only
- **Resume-safe**: Interrupted fetches can be restarted
- **Default output**: 30,000 papers (25-27K full texts)

## Usage

### Basic Run
```bash
export NCBI_API_KEY="your_key_here"  # Highly recommended (3x faster)
export UNPAYWALL_EMAIL="your@email.com"  # Required for Unpaywall

python -m agents.ingest.get_papers.pipeline \
  --mode bootstrap \
  --target 30000 \
  --fulltext-concurrency 8
```

### Configuration Options
```bash
# Disable full-text fetching
python -m agents.ingest.get_papers.pipeline --no-fetch-fulltext

# Adjust full-text concurrency (if rate limited)
python -m agents.ingest.get_papers.pipeline --fulltext-concurrency 2

# Monthly incremental update
python -m agents.ingest.get_papers.pipeline --mode monthly

# Dry run with report
python -m agents.ingest.get_papers.pipeline --dry_report 100
```

## Scoring System

### Reliability Score (0-20+ points)

Every paper gets scored on objective quality indicators:

**Study Type (1-12 pts)**
- Meta-analysis: 12 pts
- RCT: 10 pts  
- Crossover: 7 pts
- Cohort: 4 pts
- Other: 1 pt

**Sample Size (0-5 pts)**
- ≥1000: 5 pts
- ≥500: 4 pts
- ≥100: 3 pts
- ≥50: 2 pts
- ≥20: 1 pt

**Quality Indicators (0-8+ pts)**
- Each keyword: +1 pt
  - "systematic review", "meta-analysis"
  - "double-blind", "placebo-controlled"  
  - "randomized", "controlled trial"
  - "crossover", "longitudinal"

**Journal Impact (0-2 pts)**
- High-impact sports nutrition journals: +2 pts

**Recency (0-1 pts)**
- Published 2020+: +1 pt

**Diversity Adjustment (±3 pts)**
- Under-represented supplements: +3 pts
- Over-represented supplements: -3 pts

### Quality Threshold

- **Bootstrap mode**: 2.0 (balanced)
- **Monthly mode**: 2.0 (consistent)

Papers below threshold are excluded unless needed for minimum quotas.

## Enhanced Quota System

### Strategy
**Dual-level protection** ensures both quality and coverage:

1. **Top 10 Overall**: Best papers for each supplement (by quality score)
2. **Top 2 Per Goal**: Best papers for each supplement×goal combination
3. **Overlaps Allowed**: Set union typically results in 10-14 protected per supplement
4. **Full-Text Preference**: When quality scores equal, prefer papers with full-text

### Expected Protected Counts
- Universal supplements (6 goals): 12-14 protected papers
- Multi-goal supplements (3-4 goals): 11-12 protected papers
- Focused supplements (1-2 goals): 10-11 protected papers
- **Total**: ~715 protected papers (2.4% of 30K corpus)

### Benefits
- Every supplement: Minimum 10 quality papers
- Every supplement×goal combo: Minimum 2 papers
- Natural adaptation: Popular supplements get more protection
- Room for full-text optimization within protected sets

## Diversity Filtering

### Goal
Prevent corpus domination by popular supplements while maximizing full-text coverage.

### Method
If papers > 30,000 threshold:
1. Calculate supplement-goal combination frequencies
2. Assign rarity weights (rare combos get boost)
3. Add combination score to reliability score = **enhanced score**
4. Iteratively eliminate lowest-scoring papers in rounds
5. **Tiebreaking (NEW)**: When scores within 0.8, prefer full-text
6. Protected papers never eliminated

### Result
Balanced representation across:
- 63 supplements
- 6 training goals (strength, hypertrophy, endurance, etc.)
- Study types (meta, RCT, crossover, etc.)
- Journals and populations
- **85-90% full-text coverage** (quality never compromised)

## Full-Text Fetching

### Overview
**Default: Enabled** — Dual-source strategy fetches from PMC + Unpaywall for maximum coverage.

### How It Works
1. **PMC Primary** (73% full-text, 20% abstract-only):
   - ELink: Check if paper is in PMC (PMID → PMCID)
   - EFetch: Download full XML from PMC
   - Extract: Parse XML to clean, LLM-ready text
   - Quality Check: Detect if body sections present or abstract-only
   
2. **Unpaywall Rescue** (for PMC failures/abstract-only):
   - API Query: Check Unpaywall for DOI availability
   - PDF Fetch: Download full PDF when available
   - Extract: Parse PDF to text (pypdf)
   - Quality Check: Verify body sections present
   - Expected: Rescues 50-70% of PMC abstract-only papers
   
3. **Store**: Save in centralized, deduplicated repository

### What Gets Extracted
✅ **Kept** (all research value):
- Article title
- Complete abstract
- Full body (Introduction, Methods, Results, Discussion)
- Statistical details (effect sizes, p-values, CIs)
- Dosing protocols, safety data
- Table captions and data
- Figure captions

❌ **Removed** (metadata noise):
- Journal info, ISSNs, ORCIDs
- Reference bibliographies
- Empty citation brackets

### Storage Model
```
data/fulltext_store/              # Centralized (shared across runs)
├── 46/fb/pmid_12345678.json     # 2-level SHA1 sharding
├── e4/d9/pmid_87654321.json
└── ...

data/ingest/runs/<run_id>/
└── fulltext_manifest.json        # Per-run tracking only
```

### Expected Results
- **PMC Coverage**: ~73% true full-text, ~20% abstract-only, ~7% not in PMC
- **Unpaywall Rescue**: ~50-70% success on PMC abstract-only papers
- **Combined Full-Text**: 85-90% of papers (25,000-27,000 of 30k)
- **Final Abstract-Only**: 10-15% (3,000-5,000 papers)
- **Hybrid Content**: All 30k papers have content (full text preferred, abstract as fallback)
- **Why high coverage**: Quality-filtered papers tend to be in open-access journals + dual sources
- **File Size**: ~30 KB per full-text (XML or PDF extracted)
- **Total Storage**: ~900 MB for 30k papers

### Performance

| Papers | Without API Key | With API Key |
|--------|----------------|--------------|
| 1,000 | ~60 min | ~20 min |
| 10,000 | ~10 hrs | ~3 hrs |
| 30,000 | ~30 hrs | ~10 hrs |

### Configuration

#### Required/Recommended
```bash
export NCBI_API_KEY="your_key"           # Get from NCBI account (3x faster)
export NCBI_EMAIL="you@example.com"      # Required by PubMed
export UNPAYWALL_EMAIL="you@example.com" # Required by Unpaywall
```

#### Enhanced Quota System
```bash
export USE_ENHANCED_QUOTAS=true          # Use 10 overall + 2 per goal (default)
export MIN_OVERALL_PER_SUPPLEMENT=10     # Top N overall per supplement
export MIN_PER_SUPPLEMENT_GOAL=2         # Top N per supplement×goal combo
export PREFER_FULLTEXT_IN_QUOTAS=true    # Tiebreaker for protected selection
```

#### Diversity Tiebreaking
```bash
export DIVERSITY_TIEBREAK_THRESHOLD=0.8  # Score difference for full-text tiebreak
export PREFER_FULLTEXT_IN_DIVERSITY=true # Enable tiebreaking in diversity rounds
```

#### Full-Text Fetching
```bash
export ENABLE_UNPAYWALL=true             # Enable Unpaywall rescue (default: ON)
export FULLTEXT_STORE_DIR="custom/path"  # Storage location

# CLI flags
--fetch-fulltext / --no-fetch-fulltext   # Enable/disable (default: ON)
--fulltext-concurrency N                 # Parallel requests (default: 8)
--fulltext-limit N                       # Cap fetch count (default: unlimited)
```

### Rate Limiting
- **Without API key**: 3 requests/sec (NCBI limit)
- **With API key**: 10 requests/sec
- **Auto-retry**: Exponential backoff on 429 errors (1s, 5s, 15s)

## Operating Modes

### Bootstrap
- Initial database population
- Searches papers from 1990-present
- Default target: 30,000 papers
- Quality threshold: 2.0
- Diversity filtering with minimum quotas

### Monthly
- Incremental updates
- Fetches papers since last run (watermark-based)
- Quality threshold: 2.0
- Top-K selection if below diversity threshold

## Environment Variables

### Required
```bash
NCBI_EMAIL="you@example.com"      # Required by PubMed
```

### Recommended
```bash
NCBI_API_KEY="your_key"           # 3x faster full-text fetching
```

### Optional
```bash
# Targets and thresholds
INGEST_LIMIT=30000                # Target paper count
QUALITY_FLOOR_BOOTSTRAP=2.0       # Quality threshold
DIVERSITY_ROUNDS_THRESHOLD=30000  # Iterative filtering threshold

# Minimum quotas
MIN_PER_SUPPLEMENT=3              # Min papers per supplement
INCLUDE_LOW_QUALITY_IN_MIN=true   # Include low-quality to meet quotas
RARE_THRESHOLD=5                  # Threshold to consider supplement "rare"

# Storage
RUNS_BASE_DIR=data/ingest/runs    # Run output directory
KEEP_LAST_RUNS=8                  # Auto-prune old runs
FULLTEXT_STORE_DIR=data/fulltext_store

# Logging
LOG_LEVEL=info
```

## Outputs

### Per-Run Artifacts
```
data/ingest/runs/<timestamp>/
├── pm_papers.jsonl              # Selected papers (JSONL)
├── metadata.json                # Run stats and config
├── protected_quota_report.json  # Quota tracking
└── fulltext_manifest.json       # Full-text fetch summary

data/ingest/runs/latest.json     # Pointer to latest run
```

### Centralized Full-Text Store
```
data/fulltext_store/
├── 46/fb/pmid_12345678.json
├── e4/d9/pmid_87654321.json
└── ...                           # ~9,000-12,000 papers
```

## Paper Schema

Each paper in `pm_papers.jsonl` includes:

```json
{
  "id": "pmid_12345678_chunk_0",
  "pmid": "12345678",
  "doi": "10.1234/example",
  "title": "Study Title",
  "journal": "Journal Name",
  "year": 2024,
  "content": "Abstract text...",
  
  "study_type": "meta-analysis",
  "supplements": "creatine,protein",
  "primary_goal": "strength",
  "population": "trained athletes",
  "sample_size": 150,
  
  "reliability_score": 15.5,
  "combination_score": 0.8,
  "enhanced_score": 16.3,
  
  "url_pub": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
}
```

## Troubleshooting

### 429 Rate Limit Errors
**Problem**: Too many requests to NCBI  
**Solution**: 
- Get NCBI API key (3x rate limit increase)
- Reduce `--fulltext-concurrency` to 1-2
- System auto-retries with backoff

### Low Full-Text Coverage
**Expected**: Only 30-40% in PMC  
**Not a problem**: Abstracts sufficient for most papers  
**Coverage varies**: Newer papers, open journals better

### Slow Performance
**Bottleneck**: PMC fetching (~10 hours for 30k)  
**Solutions**:
- Get NCBI API key (3x faster)
- Increase `--fulltext-concurrency` to 4-8 (if have API key)
- Run overnight

### Interrupted Fetch
**Solution**: Just re-run the same command  
**Behavior**: Automatically skips existing papers (resume-safe)

## Advanced Usage

### Standalone Full-Text Fetch
```bash
# Fetch for existing run
python -m agents.ingest.get_papers.fulltext_fetcher \
  --jsonl data/ingest/runs/latest/pm_papers.jsonl \
  --concurrency 2 \
  --limit 5000
```

### Custom Store Location
```bash
export FULLTEXT_STORE_DIR="/mnt/large-drive/fulltext"
python -m agents.ingest.get_papers.pipeline --mode bootstrap
```

## Dependencies

```bash
pip install -r requirements.txt
```

Requirements:
- httpx (async HTTP)
- xmltodict (PubMed XML parsing)
- beautifulsoup4 + lxml (PMC content extraction)
- python-dateutil (date handling)

## More Information

- **[paper_processor README](../paper_processor/README.md)** - GPU/LLM processing details
- **[Main Agent README](../README.md)** - Architecture overview
- **[Project README](../../../README.md)** - Full EvidentFit system

