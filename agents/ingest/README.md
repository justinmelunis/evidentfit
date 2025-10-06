# Agent A: Research Ingestion Pipeline

Build and maintain a high-quality research corpus with automated monthly updates.

## Quick Start

### Initial Bootstrap (One-Time Setup)

Build the initial 30,000-paper corpus (~2 weeks total):

```bash
# Step 1: Fetch & select 30k papers (~10 hours with API key)
export NCBI_API_KEY="your_key"          # Get from https://www.ncbi.nlm.nih.gov/account/
export NCBI_EMAIL="you@example.com"
export UNPAYWALL_EMAIL="you@example.com"

python -m agents.ingest.get_papers.pipeline \
  --mode bootstrap \
  --target 30000 \
  --fulltext-concurrency 8

# Output: 30k papers (90% full-text) in data/ingest/runs/<timestamp>/
```

```bash
# Step 2: Process with GPU (~5 days on RTX 3080)
python -m agents.ingest.paper_processor.run \
  --max-papers 30000 \
  --batch-size 1

# Output: Structured summaries in data/paper_processor/summaries/
```

**Done!** You now have 30,000 high-quality research summaries.

---

## Monthly Updates

After bootstrap, run monthly to keep corpus fresh with new research:

### Monthly Workflow (Run Once Per Month)

```bash
# Phase 1: Fetch new papers since last run (~2-3 hours)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000

# Automatically:
# ✓ Reads watermark from last run
# ✓ Fetches only papers published since then (~4K new papers)
# ✓ Applies per-supplement quality thresholds
# ✓ Guarantees top 2-10 most recent per supplement
# ✓ Fetches full-text for selected papers
# ✓ Updates watermark for next month
# 
# Output: ~800-1,200 quality papers added
```

```bash
# Phase 2: Process new papers with GPU (~18-24 hours)
python -m agents.ingest.paper_processor.run \
  --mode monthly \
  --master-summaries data/paper_processor/master/summaries_master.jsonl \
  --max-papers 2000
```

**What happens:**
- ✓ get_papers: ~4K papers fetched → ~900 selected (quality-filtered)
- ✓ paper_processor: Loads 30K dedupe keys → processes ~850 NEW → appends to master
- ✓ Auto-backup master, save monthly delta, rebuild index, validate
- ✓ Expected: ~800-900 papers added to corpus/month (stable)

---

## How It Works

### Stage 1: get_papers (Fast, No LLM)

Fetches and selects research papers using rule-based quality scoring:

```
PubMed Search (63 supplements) → ~190K PMIDs
  ↓
Parse & Score (reliability 0-20) → ~125K human studies
  ↓
Monthly Filter (if monthly mode) → ~1K papers
  ↓
Quality Filter (≥2.0 threshold) → ~69K quality papers
  ↓
Diversity Selection (balanced) → 30K selected
  ↓
Full-Text Fetch (PMC + Unpaywall) → 90% full-text coverage
```

**Runtime**: 10 hours (with API key)  
**Cost**: $0 (free APIs)

### Stage 2: paper_processor (GPU + Mistral-7B)

Generates structured Q&A summaries using local LLM:

```
Stream papers from disk → Low RAM
  ↓
Smart chunking → Handle long full texts
  ↓
Two-pass Mistral-7B → Strict prompt + repair
  ↓
Merge chunks → Doc-level summary
  ↓
Stream write → Resume-safe output
```

**Runtime**: 5 days (RTX 3080, ~4-5 papers/min)  
**Cost**: $0 vs $22,500 cloud LLM cost

---

## Monthly Update Strategy

### How Monthly Mode Works

#### Bootstrap vs Monthly

| Aspect | Bootstrap (Once) | Monthly (Recurring) |
|--------|------------------|---------------------|
| **Papers Fetched** | ~190K (all time) | ~4K (since last run) |
| **Quality Filter** | 2.0 minimum | Per-supplement thresholds |
| **Papers Added** | 30,000 | ~800-1,200 |
| **Runtime** | ~10 hours | ~2-3 hours |
| **Purpose** | Build initial corpus | Keep fresh |

#### Monthly Quality Thresholds

**Hard-coded thresholds** (never change month-to-month):

**Small supplements** (<100 papers):
- Use **P25** (25th percentile) threshold
- Accept top **2** most recent per month
- Examples: raspberry-ketone (1.75), synephrine (3.50), betaine (4.50)

**Large supplements** (≥100 papers):
- Use **Median** (50th percentile) threshold
- Accept top **10** most recent per month  
- Examples: caffeine (4.00), creatine (4.00), vitamin-d (5.00)

**Why fixed?** Provides stable, predictable monthly growth (~800-1,200 papers)

#### What Gets Added

**Always added** (bypass thresholds):
- Meta-analyses and systematic reviews
- Exceptional quality papers (≥4.5)
- Top 2-10 most recent per supplement (if ≥2.5 quality)

**Added if above threshold**:
- Single-supplement papers above threshold
- Multi-supplement papers if they qualify for ANY tag

**Example**: 
- New caffeine paper (quality 3.8) → ❌ Rejected (below 4.0 threshold)
- Same paper also tags raspberry-ketone → ✅ Accepted (above 1.75 threshold)
- Final tags: `raspberry-ketone` only (caffeine tag removed)

### Expected Monthly Outputs

| Month | Papers Fetched | Pass Monthly Filter | Final Selected | Corpus Size |
|-------|----------------|---------------------|----------------|-------------|
| 0 (Bootstrap) | ~190K | N/A | 30,000 | 30,000 |
| 1 | ~4,000 | ~1,000 | ~900 | ~30,900 |
| 2 | ~4,000 | ~1,050 | ~950 | ~31,850 |
| 6 | ~4,000 | ~1,100 | ~1,000 | ~35,000 |
| 12 | ~4,000 | ~1,150 | ~1,050 | ~41,000 |

**Growth rate**: ~10,000-12,000 papers/year (sustainable, manageable)

---

## One-Time Setup (After Bootstrap Completes)

Run these steps once to prepare for monthly updates:

### 1. Generate Monthly Thresholds

After get_papers bootstrap finishes:

```bash
# Analyze bootstrap corpus and generate hard-coded thresholds
python scripts/generate_monthly_thresholds.py data/ingest/runs/<timestamp>/pm_papers.jsonl

# This creates: agents/ingest/get_papers/monthly_thresholds.py (80 supplements)
# Review the thresholds, then commit:
git add agents/ingest/get_papers/monthly_thresholds.py
git commit -m "Set monthly quality thresholds from bootstrap corpus"
```

### 2. Initialize Master Summaries

After paper_processor bootstrap completes:

```bash
# Create directory structure
mkdir -p data/paper_processor/master
mkdir -p data/paper_processor/monthly_deltas

# Designate bootstrap output as master
cp data/paper_processor/summaries/summaries_<timestamp>.jsonl \
   data/paper_processor/master/summaries_master.jsonl

# Save bootstrap as first delta (audit trail)
cp data/paper_processor/master/summaries_master.jsonl \
   data/paper_processor/monthly_deltas/2025-10-05_bootstrap.jsonl

# Build initial index
python -c "from agents.ingest.paper_processor.storage_manager import StorageManager; \
from pathlib import Path; \
s = StorageManager(); \
idx = s.build_master_index(Path('data/paper_processor/master/summaries_master.jsonl')); \
s.save_master_index(idx, Path('data/paper_processor/master/summaries_master.jsonl')); \
print(f'Index built: {len(idx):,} entries')"
```

### 3. Validate Setup

```bash
# Verify master is valid
python scripts/validate_master_summaries.py
```

**Now you're ready for monthly updates!**

---

## Components

### get_papers
Fast paper discovery, selection, and full-text fetching.

- ⚡ **No LLM calls** - Rule-based for speed (zero cost)
- 🎯 **Quality scoring** - Meta-analyses, RCTs, sample size
- 🔄 **Monthly mode** - Watermark-based incremental updates
- 📄 **Full-text fetching** - PMC + Unpaywall (90%+ coverage)
- 🎲 **Diversity filtering** - Balanced across supplements and goals

**Runtime**: ~10 hours (30K papers with API key)

📖 **[Technical Documentation](get_papers/README.md)** - Algorithms, scoring, monthly system

### paper_processor
GPU-accelerated LLM processing for structured summaries.

- 🎮 **Local GPU** - Mistral-7B on RTX 3080 (10GB VRAM)
- 🔧 **Optimized** - 4-bit quant, streaming I/O, smart chunking
- 📝 **Two-pass extraction** - Strict prompt + targeted repair
- 💾 **Resume-safe** - Streaming output, resume from interruptions
- 📊 **Rich telemetry** - Progress, full-text usage, performance

**Runtime**: ~5 days (30K papers on RTX 3080)

📖 **[Technical Documentation](paper_processor/README.md)** - GPU setup, configuration

---

## Outputs

### Bootstrap Run

```
data/ingest/runs/20251005_172726/
├── pm_papers.jsonl              # 30,000 selected papers
├── metadata.json                # Run statistics
├── protected_quota_report.json  # Quota system details
└── fulltext_manifest.json       # Full-text fetch summary

data/fulltext_store/             # Centralized (shared across runs)
└── <shard>/<shard>/             # ~27K full texts (~900 MB)

data/paper_processor/
├── summaries/summaries_<timestamp>.jsonl  # 30K structured summaries
└── stats/stats_<timestamp>.json           # Processing statistics
```

### Monthly Run

```
data/ingest/runs/20251105_xxxxxx/
├── pm_papers.jsonl              # ~900 new papers
├── metadata.json                # Includes monthly filter stats
└── fulltext_manifest.json       # +800-900 new full texts

data/fulltext_store/             # Incremental additions
└── <shard>/<shard>/             # +800-900 new full texts

data/paper_processor/
├── master/
│   ├── summaries_master.jsonl            # Appended ~850 summaries (30K → 30.85K)
│   ├── summaries_master.jsonl.backup_*   # Auto-created before append
│   └── master_index.json                 # Rebuilt after append
├── monthly_deltas/
│   └── 2025-11-05_delta.jsonl            # ~850 papers with metadata
└── stats/
    └── stats_<timestamp>.json            # Monthly run statistics
```

---

## Monitoring

### Check Current Run Progress

```bash
# View latest log
Get-Content logs\get_papers_<timestamp>.log -Tail 30

# Check key milestones
Select-String -Path logs\get_papers_<timestamp>.log -Pattern 'unique papers|COMPLETE|WARNING|ERROR' | Select-Object -Last 10
```

### Analyze Corpus Quality

```bash
# View quality distribution per supplement
python scripts/analyze_corpus_quality.py data/ingest/runs/<timestamp>/pm_papers.jsonl
```

### Check Full-Text Coverage

```bash
# Review full-text fetch statistics
cat data/ingest/runs/<timestamp>/fulltext_manifest.json | jq '.coverage'
```

### Monthly Growth Trends

```bash
# Analyze monthly additions over time
python scripts/monthly_growth_report.py

# Validate master summaries (check for duplicates)
python scripts/validate_master_summaries.py
```

---

## Troubleshooting

### get_papers Issues

| Problem | Solution |
|---------|----------|
| **429 Rate Limit** | Get NCBI API key or reduce `--fulltext-concurrency` |
| **Timeout Errors** | Auto-retries (3 attempts) - no action needed |
| **Low PMC Coverage** | Enable Unpaywall (set `UNPAYWALL_EMAIL`) |
| **Run Interrupted** | Safe to re-run - full-text fetching auto-dedupes |

### paper_processor Issues

| Problem | Solution |
|---------|----------|
| **CUDA Out of Memory** | Use `--batch-size 1` (default), reduce `--ctx-tokens` |
| **Slow Processing** | Expected: ~4-5 papers/min on RTX 3080 |
| **Run Interrupted (bootstrap)** | Use `--resume-summaries <path>.jsonl.tmp` |
| **Run Interrupted (monthly)** | Re-run from start - cross-run dedupe prevents duplicates |
| **Missing Fields** | Two-pass extraction auto-repairs missing fields |
| **Master Validation Failed** | Restore from `.backup_*` file, re-run monthly |
| **Duplicates in Master** | Run `rebuild_master_from_deltas.py` to rebuild clean master |

---

## Performance

### get_papers (30K Papers)

| Configuration | PMC Fetch | Full Pipeline | Full-Text Coverage |
|---------------|-----------|---------------|-------------------|
| With API key + Unpaywall | ~3-4 hrs | ~10 hrs | 90%+ |
| With API key only | ~3-4 hrs | ~8 hrs | 73% |
| No API key + Unpaywall | ~10-12 hrs | ~30 hrs | 90%+ |

### paper_processor (30K Papers)

| Hardware | VRAM | Papers/Min | Total Time |
|----------|------|------------|------------|
| RTX 4090 (24GB) | ~8GB | ~6-7 | ~3.5 days |
| RTX 3080 (10GB) | ~7GB | ~4-5 | ~5 days |
| RTX 3070 (8GB) | ~6GB | ~3-4 | ~7 days |

**Note**: Batch size >1 not recommended (OOM risk, minimal speedup)

---

## Technical Details

For implementation details, algorithms, and configuration options:

- 📖 **[get_papers Technical Reference](get_papers/README.md)** - Scoring algorithms, monthly threshold system, full-text architecture
- 📖 **[paper_processor Technical Reference](paper_processor/README.md)** - GPU optimization, chunking, two-pass extraction

---

## Monthly Maintenance Schedule

**Recommended**: First week of each month

```bash
# Monday: Kick off get_papers monthly run (~2-3 hours)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000

# Tuesday-Wednesday: Process new papers with GPU (~1-2 days)  
python -m agents.ingest.paper_processor.run --max-papers 2000

# Thursday: Verify outputs, regenerate banking if needed
python scripts/analyze_corpus_quality.py data/ingest/runs/latest/pm_papers.jsonl
```

**Time commitment**: ~2-3 days/month (mostly unattended GPU processing)

---

## What You Get

### After Bootstrap
- **30,000 research papers** covering 63 supplements
- **90% full-text coverage** (27-28K full texts + 2-3K abstracts)
- **Balanced diversity** across supplements, study types, goals
- **Quality-assured** (all papers ≥2.0 reliability score)
- **Ready for Q&A** - Structured summaries with evidence grades

### After Monthly Updates
- **+800-1,200 papers/month** (stable growth)
- **Quality-maintained** - Fixed thresholds prevent dilution
- **Fresh research** - Top 2-10 most recent per supplement guaranteed
- **Smart additions** - Improves weak supplements, maintains strong ones
- **Predictable** - Same thresholds month-to-month

---

## Understanding the Pipeline

### Why Two Stages?

**Stage 1 (get_papers)** - Fast selection without LLM:
- ✅ Process 190K candidates in hours (not days)
- ✅ Zero cost (no LLM API calls)
- ✅ High recall (don't miss important papers)

**Stage 2 (paper_processor)** - Deep analysis with LLM:
- ✅ Only process selected papers (30K not 190K)
- ✅ Local GPU (zero ongoing cost)
- ✅ High-quality structured output

**Total cost**: GPU electricity (~$20) vs Cloud LLM (~$22,500)

### Why Monthly Updates?

**New research published constantly:**
- ~4,000 new papers/month in PubMed (exercise + supplements)
- Meta-analyses synthesizing latest evidence
- RCTs with new protocols, populations, outcomes

**Benefits:**
- 📅 **Stay current** - Latest research within 30 days
- 🎯 **Quality-aware** - Only add papers that improve corpus
- 💾 **Manageable** - ~1,000 papers/month vs 30K all at once
- ⚡ **Fast** - 2-3 hours/month vs weeks for full rebuild

---

## File Structure

```
agents/ingest/
├── get_papers/                  # Stage 1: Paper fetching
│   ├── pipeline.py              # Main orchestrator
│   ├── pubmed_client.py         # NCBI E-utilities API
│   ├── parsing.py               # XML parsing & scoring
│   ├── diversity.py             # Selection algorithms
│   ├── fulltext_fetcher.py      # PMC + Unpaywall integration
│   ├── monthly_filter.py        # Monthly quality filtering
│   ├── monthly_thresholds.py    # Hard-coded thresholds
│   └── README.md                # Technical documentation
│
├── paper_processor/             # Stage 2: LLM processing
│   ├── run.py                   # Main orchestrator
│   ├── mistral_client.py        # HuggingFace Transformers
│   ├── schema.py                # Prompts & validation
│   ├── storage_manager.py       # Streaming I/O
│   └── README.md                # Technical documentation
│
└── README.md                    # This file (user guide)
```

```
data/
├── ingest/
│   ├── runs/<timestamp>/        # Per-run outputs
│   │   ├── pm_papers.jsonl
│   │   ├── metadata.json
│   │   └── fulltext_manifest.json
│   ├── watermark.json           # Monthly update tracking
│   └── latest.json              # Pointer to most recent run
│
├── fulltext_store/              # Centralized full-text repository
│   └── <shard>/<shard>/         # Sharded by PMID/DOI
│
└── paper_processor/
    ├── summaries/               # Per-run summaries
    ├── stats/                   # Processing statistics
    ├── master/                  # Master summaries (TODO)
    │   └── summaries_master.jsonl
    └── monthly_deltas/          # Monthly audit trail (TODO)
```

---

## Next Steps

After bootstrap completes:

1. ✅ **Verify outputs** - Check metadata.json for statistics
2. ✅ **Generate thresholds** - Run `generate_monthly_thresholds.py`
3. ✅ **Set up master** - Initialize paper_processor master directory
4. ✅ **Schedule monthly** - Set reminder for first week of each month
5. ✅ **Monitor quality** - Run `analyze_corpus_quality.py` periodically

---

## Additional Resources

### Scripts

- `scripts/generate_monthly_thresholds.py` - Generate hard-coded thresholds (one-time)
- `scripts/analyze_corpus_quality.py` - View quality distribution per supplement
- `scripts/check_low_quality_papers.py` - Investigate low-quality papers

### Documentation

- 📖 **[get_papers Technical Reference](get_papers/README.md)**
- 📖 **[paper_processor Technical Reference](paper_processor/README.md)**
- 📖 **[Project README](../../README.md)** - Overall EvidentFit architecture
- 📖 **[Methodology](../../docs/METHODOLOGY_PUBLIC.md)** - Public-facing methodology

---

## Support

### Getting Help

- Check logs: `logs/get_papers_<timestamp>.log`
- Review metadata: `data/ingest/runs/latest/metadata.json`
- Analyze quality: `python scripts/analyze_corpus_quality.py <path>`

### Common Questions

**Q: How long does bootstrap take?**  
A: ~10 hours (get_papers) + ~5 days (paper_processor) = ~5.5 days total

**Q: Can I run monthly updates while paper_processor is still running?**  
A: Yes! get_papers and paper_processor are independent

**Q: What if I miss a monthly update?**  
A: No problem - watermark is based on date, not sequential runs. Just run when ready.

**Q: Can I adjust monthly thresholds?**  
A: Yes, manually edit `monthly_thresholds.py` and commit changes

**Q: What if get_papers is interrupted?**  
A: Safe to re-run - full-text fetching auto-deduplicates, no duplicate work

