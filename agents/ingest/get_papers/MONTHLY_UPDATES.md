# Monthly Update System

## Overview

The monthly update system adds new research papers to your corpus while maintaining quality and avoiding redundancy. It uses **hard-coded, stable thresholds** based on your bootstrap corpus quality.

## Key Principles

1. **Hard-coded thresholds** - Never change month-to-month (predictable, explainable)
2. **Per-supplement evaluation** - Each supplement judges papers independently
3. **Recency guarantee** - Always include top N most recent papers per supplement
4. **Multi-supplement handling** - Papers qualify via their weakest (lowest threshold) supplement

## How It Works

### Phase 1: Fetch New Papers (get_papers)

```bash
# Run monthly (uses watermark to fetch only new papers)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 5000
```

**What happens:**
1. Reads watermark (`data/ingest/watermark.json`) from last run
2. Fetches papers published since last run (mindate = watermark - 1 day)
3. **Applies monthly quality filter** (new step)
4. Proceeds with normal selection (diversity, full-text fetch)
5. Updates watermark for next month

---

## Monthly Quality Filter (Three-Tier System)

### Tier 1: Always Add (Bypass Thresholds)

Papers that ALWAYS qualify for a supplement:

```python
✅ Meta-analyses
✅ Systematic reviews
✅ Exceptional quality (≥4.5)
✅ Top N most recent per supplement:
   - Large supplements (500+ papers): Top 10
   - Small supplements: Top 2
   (Must meet minimum 2.5 quality)
```

### Tier 2: Quality Threshold

Papers must meet hard-coded threshold for each supplement tag:

**Small Corpora (<100 papers in bootstrap):**
- Threshold = P25 (25th percentile)
- Examples:
  - `raspberry-ketone`: 1.5 (only 3 papers, build diversity)
  - `synephrine`: 3.5 (23 papers, still building)
  - `betaine`: 4.5 (95 papers, approaching maturity)

**Large Corpora (≥100 papers in bootstrap):**
- Threshold = Median (50th percentile)
- Examples:
  - `caffeine`: 4.0 (1,016 papers, mature corpus)
  - `creatine`: 4.0 (1,628 papers, mature corpus)
  - `vitamin-d`: 5.0 (1,825 papers, very high quality)

### Tier 3: Reject

Papers below threshold for ALL their supplement tags are rejected completely.

---

## Multi-Supplement Paper Example

**Paper**: PMID 99999999
- **Tags**: `caffeine`, `raspberry-ketone`, `protein`
- **Quality**: 3.8
- **Year**: 2025

**Evaluation per supplement:**

| Supplement | Threshold | 3.8 ≥ Threshold? | Include? | Reason |
|------------|-----------|------------------|----------|--------|
| `caffeine` | 4.0 | ❌ No | Reject | Below threshold |
| `raspberry-ketone` | 1.5 | ✅ Yes | **Accept** | Above threshold |
| `protein` | 4.0 | ❌ No | Reject | Below threshold |

**Result:**
- ✅ Paper is INCLUDED
- **Final tags**: `raspberry-ketone` only
- **Removed tags**: `caffeine`, `protein` (tracked in `_removed_supplements`)

**Benefit**: Paper helps build raspberry-ketone corpus without diluting caffeine/protein corpora.

---

## Recency Guarantee

Ensures fresh research is always included, even if quality is slightly below threshold.

### Configuration

```python
RECENCY_TOP_N = {
    "default": 2,  # Top 2 for small supplements
    "large_supplements": [
        "arginine", "caffeine", "creatine", "iron", 
        "magnesium", "nitrate", "omega-3", "protein", "vitamin-d"
    ],
    "large_supplement_n": 10,  # Top 10 for large supplements
}
```

### Example (November 2025)

**Caffeine** (large supplement):
- 50 new papers published this month
- Sort by year (desc), then PMID
- Take top 10 that have quality ≥ 2.5
- These 10 are guaranteed inclusion (even if below 4.0 threshold)

**Raspberry-ketone** (small supplement):
- 5 new papers published this month
- Take top 2 that have quality ≥ 2.5
- These 2 are guaranteed inclusion

**Why:** Keeps corpus fresh with latest research, even if study quality hasn't caught up yet.

---

## Expected Monthly Growth

### Month 1 (After Bootstrap)

**Input**: ~4,000 new papers from PubMed

**Filtering:**
```
4,000 papers from PubMed
  ↓ Monthly quality filter
  ├─ Tier 1 (Always add): ~150 papers
  │   ├─ Meta-analyses: ~50
  │   ├─ Exceptional (≥4.5): ~50
  │   └─ Recency top N: ~50
  ├─ Tier 2 (Threshold): ~800 papers
  │   ├─ Large supplements: ~600 (above median)
  │   └─ Small supplements: ~200 (above P25)
  └─ Tier 3 (Reject): ~3,050 papers
     ├─ Below all thresholds: ~2,500
     └─ Multi-supp rejected: ~550

~950 papers → Diversity selection (target ~800-1,000)
  ↓
~900 papers added to corpus
```

### Month 6 (Mature Corpus)

**Expected**: ~800-1,200 papers/month (stable, no decline)

**Why stable?** Thresholds are FIXED based on bootstrap corpus. As long as PubMed publication rates stay consistent, monthly additions remain predictable.

---

## File Structure

```
agents/ingest/get_papers/
├── monthly_thresholds.py       # Hard-coded thresholds (generated once)
├── monthly_filter.py           # Filtering logic
└── pipeline.py                 # Integrates monthly filter at Step 2.5

scripts/
└── generate_monthly_thresholds.py  # One-time generation script
```

---

## Usage

### First Time Setup (After Bootstrap)

```bash
# 1. Generate hard-coded thresholds from bootstrap corpus
python scripts/generate_monthly_thresholds.py data/ingest/runs/<bootstrap_run>/pm_papers.jsonl

# This creates: agents/ingest/get_papers/monthly_thresholds.py
# COMMIT THIS FILE - it never changes!
```

### Monthly Run

```bash
# Just run in monthly mode (uses watermark automatically)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000

# The monthly filter runs automatically:
# - Loads hard-coded thresholds
# - Applies recency guarantee
# - Evaluates per-supplement
# - Filters supplement tags
```

---

## Thresholds File

See `agents/ingest/get_papers/monthly_thresholds.py` for the complete list.

**Small supplements (<100 papers):**
- `raspberry-ketone`: 1.5
- `ecdysteroids`: 2.0
- `synephrine`: 3.5
- `betaine`: 4.5

**Large supplements (≥100 papers):**
- `caffeine`: 4.0
- `creatine`: 4.0
- `beta-alanine`: 4.5
- `vitamin-d`: 5.0

**These never change** - they're based on your bootstrap corpus quality and provide a stable quality bar.

---

## Monitoring

### Removal Stats (Logged Automatically)

```
Monthly filter: 4,123 → 1,087 papers
  Kept for at least one supplement: 1,087
  Rejected completely: 3,036
  Top removal reasons:
    caffeine_below_threshold_4.00: 523
    creatine_below_threshold_4.00: 412
    protein_below_threshold_4.00: 298
    ...
```

### Audit Trail

Each paper tracks:
```json
{
  "pmid": "12345678",
  "supplements": "raspberry-ketone",
  "_removed_supplements": ["caffeine", "protein"],
  "_removal_reasons": {
    "caffeine": "below_threshold_4.00",
    "protein": "below_threshold_4.00"
  }
}
```

---

## Benefits

1. ✅ **Predictable** - Thresholds never change, easy to explain
2. ✅ **Fair** - Each supplement evaluated independently
3. ✅ **Fresh** - Recency guarantee ensures latest research
4. ✅ **Balanced** - Small supplements get 2/month, large get 10/month
5. ✅ **Quality-aware** - Maintains corpus quality without over-restricting
6. ✅ **Multi-supplement smart** - Can qualify via weakest supplement

---

## Adjustments

If you need to adjust behavior:

### Change Recency Guarantee

Edit `agents/ingest/get_papers/monthly_thresholds.py`:
```python
RECENCY_TOP_N = {
    "default": 5,  # Increase from 2 to 5 for small supplements
    "large_supplement_n": 20,  # Increase from 10 to 20
}
```

### Change Minimum Quality for Recency

```python
RECENCY_MIN_QUALITY = 3.0  # Raise from 2.5 to 3.0
```

### Add New Supplement to Large List

```python
"large_supplements": [
    "arginine", "caffeine", "creatine", "iron",
    "beta-alanine",  # Add beta-alanine to get top 10/month
],
```

---

## See Also

- `agents/ingest/get_papers/monthly_thresholds.py` - Hard-coded thresholds
- `scripts/generate_monthly_thresholds.py` - Threshold generation tool
- `agents/ingest/get_papers/monthly_filter.py` - Filtering implementation

