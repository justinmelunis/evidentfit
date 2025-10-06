# Monthly Update System - Complete Guide

## Overview

The monthly update system keeps your EvidentFit research corpus fresh by adding new papers while maintaining quality and avoiding redundancy. It consists of two phases:

1. **get_papers** (Phase 1): Fetch and filter new papers from PubMed
2. **paper_processor** (Phase 2): Process new papers with LLM and append to master summaries

## Key Principles

- ✅ **Hard-coded thresholds** - Stable, predictable, explainable (never change month-to-month)
- ✅ **Per-supplement evaluation** - Each supplement judges papers independently  
- ✅ **Recency guarantee** - Always include top N most recent papers per supplement
- ✅ **Cross-run deduplication** - Never process the same paper twice
- ✅ **Append-only storage** - Build corpus incrementally, never delete

---

# Phase 1: get_papers Monthly Mode

## Quick Start

```bash
# Run once per month
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000
```

**What it does:**
1. Reads watermark from last run (only fetches papers published since then)
2. Applies monthly quality filter (hard-coded per-supplement thresholds)
3. Applies diversity selection and enhanced quotas
4. Fetches full-text for selected papers
5. Updates watermark for next month

---

## Monthly Quality Filter (Three-Tier System)

### Tier 1: Always Add (Bypass Thresholds)

These papers ALWAYS qualify, regardless of threshold:

```
✅ Meta-analyses
✅ Systematic reviews  
✅ Exceptional quality (≥4.5)
✅ Top N most recent per supplement:
   - Large supplements (500+ papers): Top 10
   - Small supplements: Top 2
   (Must meet minimum 2.5 quality)
```

### Tier 2: Quality Thresholds (Hard-Coded)

Papers must meet the hard-coded threshold for each supplement tag.

**Small Corpora (<100 papers in bootstrap):**
- Threshold = **P25** (25th percentile) - builds diversity
- Recency: Top **2** most recent per month
- Examples:
  ```
  raspberry-ketone: 1.5 (only 3 papers, build corpus)
  synephrine: 3.5 (23 papers, still building)
  betaine: 4.5 (95 papers, approaching maturity)
  ```

**Large Corpora (≥100 papers in bootstrap):**
- Threshold = **Median** (50th percentile) - maintains quality
- Recency: Top **10** most recent per month  
- Examples:
  ```
  caffeine: 4.0 (1,016 papers, mature)
  creatine: 4.0 (1,628 papers, mature)
  vitamin-d: 5.0 (1,825 papers, high quality)
  ```

**See `agents/ingest/get_papers/monthly_thresholds.py` for complete list (80 supplements)**

### Tier 3: Reject

Papers below threshold for ALL their supplement tags.

---

## Multi-Supplement Paper Handling

Papers with multiple supplement tags are evaluated **independently per supplement**.

### Example: PMID 99999999

**Paper details:**
- Tags: `caffeine`, `raspberry-ketone`, `protein`
- Quality: 3.8
- Year: 2025

**Evaluation:**

| Supplement | Threshold | 3.8 ≥ Threshold? | Decision |
|------------|-----------|------------------|----------|
| `caffeine` | 4.0 | ❌ No (3.8 < 4.0) | Reject |
| `raspberry-ketone` | 1.5 | ✅ Yes (3.8 ≥ 1.5) | **Accept** |
| `protein` | 4.0 | ❌ No (3.8 < 4.0) | Reject |

**Result:**
- ✅ Paper is INCLUDED  
- **Final tags**: `raspberry-ketone` only
- **Removed tags**: `caffeine`, `protein`
- **Tracked**: `_removed_supplements: ["caffeine", "protein"]`

**Benefit**: Paper helps build raspberry-ketone corpus without diluting caffeine/protein.

---

## Expected Monthly Growth

### Month 1 (After Bootstrap)

```
~4,000 papers from PubMed (published since last run)
  ↓
Monthly Quality Filter:
  ├─ Meta-analyses/Reviews: ~50 papers (always add)
  ├─ Exceptional (≥4.5): ~50 papers (always add)
  ├─ Recency guarantee: ~50 papers (top N per supplement)
  ├─ Above threshold: ~800 papers (quality filter)
  └─ Rejected: ~3,050 papers (below threshold)
  ↓
~950 papers pass monthly filter
  ↓
Diversity selection (target ~1,000)
  ↓
Full-text fetch
  ↓
~900 papers added to corpus
```

### Month 6+

**Expected**: ~800-1,200 papers/month (**stable, no decline**)

**Why stable?**
- Thresholds are FIXED (based on bootstrap corpus)
- As long as PubMed publication rates stay consistent (~4K/month), additions stay consistent
- Quality standards don't change month-to-month

**Only declines if:**
- ❌ PubMed publication rate drops (external factor)
- ❌ Research quality improves dramatically (rare)

Otherwise, growth is **predictable and stable**! 🎯

---

# Phase 2: paper_processor Monthly Mode

## Quick Start

```bash
# After get_papers monthly run completes
python -m agents.ingest.paper_processor.run \
  --mode monthly \
  --master-summaries data/paper_processor/master/summaries_master.jsonl \
  --max-papers 2000
```

**What it does:**
1. Loads dedupe keys from master summaries (cross-run deduplication)
2. Processes only NEW papers (skips already-processed)
3. Appends to master summaries file
4. Saves monthly delta separately (audit trail)
5. Updates master stats

---

## Master Summaries System

### File Structure

```
data/paper_processor/
├── master/
│   ├── summaries_master.jsonl          # All summaries (append-only, ~30K+ papers)
│   ├── master_stats.json                # Cumulative statistics
│   └── master_index.json                # Optional: Fast lookup {pmid: line_offset}
├── monthly_deltas/
│   ├── 2025-10-05_bootstrap.jsonl      # Initial 30K (copy for audit)
│   ├── 2025-11-05_delta.jsonl          # Month 1: +912 papers
│   ├── 2025-12-05_delta.jsonl          # Month 2: +1,087 papers
│   └── 2026-01-05_delta.jsonl          # Month 3: +1,023 papers
└── latest.json                          # Points to master
```

### Storage Strategy

**Append-Only Master:**
- Single source of truth
- Never delete papers
- Only add new ones
- Easy to query/search

**Monthly Deltas:**
- Backup/audit trail
- Enables rollback if needed
- Tracks monthly growth patterns

---

## Cross-Run Deduplication

### Current (Within-Run Only)
```python
# paper_processor currently only dedupes within a single run
seen_keys = set()  # Cleared each run
```

### Monthly (Cross-Run)
```python
# Load ALL dedupe keys from master summaries
seen_keys = load_dedupe_keys_from_master(master_path)
# ~30K keys = ~1MB RAM (negligible)

# Process papers, skip if already seen
for paper in new_papers:
    dkey = create_dedupe_key(paper)
    if dkey in seen_keys:
        skip  # Already processed in previous run
```

---

## Monthly Workflow (Both Phases)

### One-Time Setup (After Bootstrap Completes)

```bash
# 1. Create master directory structure
mkdir -p data/paper_processor/master
mkdir -p data/paper_processor/monthly_deltas

# 2. Designate bootstrap output as master
cp data/paper_processor/summaries/summaries_<timestamp>.jsonl \
   data/paper_processor/master/summaries_master.jsonl

# 3. Save bootstrap as first delta (for audit)
cp data/paper_processor/master/summaries_master.jsonl \
   data/paper_processor/monthly_deltas/2025-10-05_bootstrap.jsonl

# 4. Generate hard-coded thresholds from bootstrap
python scripts/generate_monthly_thresholds.py data/ingest/runs/<bootstrap_run>/pm_papers.jsonl

# 5. Commit the thresholds file
git add agents/ingest/get_papers/monthly_thresholds.py
git commit -m "Set monthly quality thresholds from bootstrap corpus"
```

### Monthly Run (Every Month)

```bash
# Step 1: Fetch new papers (get_papers)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000

# Output: data/ingest/runs/<run_id>/pm_papers.jsonl (~900 papers)
# Watermark automatically updated

# Step 2: Process new papers (paper_processor) 
python -m agents.ingest.paper_processor.run \
  --mode monthly \
  --master-summaries data/paper_processor/master/summaries_master.jsonl \
  --max-papers 2000

# Output: 
# - data/paper_processor/master/summaries_master.jsonl (appended ~850 papers)
# - data/paper_processor/monthly_deltas/2025-11-05_delta.jsonl (audit copy)
```

---

## Implementation Status

### ✅ Phase 1: get_papers (COMPLETE)
- [x] Watermark system
- [x] Monthly mode
- [x] Hard-coded thresholds
- [x] Monthly filter logic
- [x] Recency guarantee
- [x] Per-supplement evaluation
- [x] Multi-supplement tag filtering

### ⏳ Phase 2: paper_processor (TO DO)
- [ ] `--mode monthly` argument
- [ ] `--master-summaries` argument
- [ ] Load master dedupe keys
- [ ] Append to master (not create new file)
- [ ] Save monthly delta separately
- [ ] Update master stats

---

## Regenerating Thresholds

After your current get_papers run completes (with retry logic and no paper loss):

```bash
# Regenerate thresholds from the NEW, improved corpus
python scripts/generate_monthly_thresholds.py data/ingest/runs/<new_run_id>/pm_papers.jsonl

# This updates: agents/ingest/get_papers/monthly_thresholds.py

# Review and commit
git diff agents/ingest/get_papers/monthly_thresholds.py
git add agents/ingest/get_papers/monthly_thresholds.py
git commit -m "Update monthly thresholds from improved bootstrap corpus"
```

---

## Monitoring Monthly Updates

### Run Logs

```
STEP 2.5: APPLYING MONTHLY QUALITY FILTER
Monthly filter: 4,123 → 1,087 papers
  Kept for at least one supplement: 1,087
  Rejected completely: 3,036
  Top removal reasons:
    caffeine_below_threshold_4.00: 523
    creatine_below_threshold_4.00: 412
    protein_below_threshold_4.00: 298
    vitamin-d_below_threshold_5.00: 187
```

### Metadata Tracking

Each monthly run saves:
```json
{
  "mode": "monthly",
  "watermark_mindate": "2025/11/05",
  "papers_fetched": 4,123,
  "papers_after_monthly_filter": 1,087,
  "papers_selected": 912,
  "monthly_filter_removals": {
    "caffeine_below_threshold_4.00": 523,
    "rejected_all_supplements": 856
  }
}
```

---

## Adjusting Thresholds

Thresholds are hard-coded for stability, but you CAN manually adjust if needed.

### To Raise Quality Bar

Edit `agents/ingest/get_papers/monthly_thresholds.py`:
```python
MONTHLY_THRESHOLDS = {
    "caffeine": 4.5,  # Raise from 4.0 to 4.5 (more strict)
    # ... rest unchanged
}
```

### To Add More Recency Papers

```python
RECENCY_TOP_N = {
    "default": 5,  # Increase from 2 to 5 for small supplements
    "large_supplement_n": 20,  # Increase from 10 to 20
}
```

### To Change Large Supplement List

```python
"large_supplements": [
    "arginine", "caffeine", "creatine", "iron",
    "beta-alanine",  # ADD: Now gets top 10/month instead of 2
],
```

**Remember to commit changes** - thresholds are source code, not config!

---

## Troubleshooting

### Too Many Papers Added Per Month

**Problem**: Getting 2,000+ papers/month, too much to process

**Solutions:**
1. Raise thresholds for high-volume supplements
2. Reduce `MAX_PER_SUPPLEMENT_MONTHLY` cap
3. Lower recency guarantee counts

### Too Few Papers Added Per Month

**Problem**: Getting <500 papers/month, corpus not growing fast enough

**Solutions:**
1. Lower some thresholds (especially for weak supplements)
2. Increase recency guarantee counts
3. Lower `RECENCY_MIN_QUALITY` from 2.5 to 2.0

### Supplement Imbalance

**Problem**: One supplement dominates monthly additions

**Check thresholds:**
```bash
python scripts/analyze_corpus_quality.py data/ingest/runs/<run_id>/pm_papers.jsonl
```

**Adjust if needed** - raise threshold for dominant supplement

---

## Benefits

### Predictable Growth
- Fixed thresholds = consistent monthly additions (~800-1,200 papers)
- No algorithmic drift over time
- Easy to budget processing time

### Quality Maintenance
- High-quality supplements maintain high standards (median threshold)
- Low-quality supplements still build diversity (P25 threshold)
- Never dilute strong corpora with weak papers

### Freshness Guarantee
- Top 2-10 most recent papers per supplement always included
- Keeps cutting-edge research in corpus
- Even if quality standards haven't caught up yet

### Smart Multi-Supplement Handling
- Papers can qualify via weakest supplement
- But tags are filtered per-supplement
- Prevents low-quality multi-ingredient studies from diluting focused corpora

---

## See Also

- **get_papers**: `agents/ingest/get_papers/README.md` - Paper fetching and selection
- **paper_processor**: `agents/ingest/paper_processor/README.md` - LLM processing
- **Thresholds**: `agents/ingest/get_papers/monthly_thresholds.py` - Hard-coded values
- **Main README**: `agents/ingest/README.md` - Overall architecture

