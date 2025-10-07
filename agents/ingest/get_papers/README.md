# get_papers - Technical Reference

Fast, LLM-free pipeline for discovering, selecting, and fetching research papers from PubMed with balanced diversity and dual-source full-text coverage.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Reliability Scoring](#reliability-scoring)
- [Selection Pipeline](#selection-pipeline)
- [Full-Text Fetching](#full-text-fetching)
- [Monthly Update System](#monthly-update-system)
- [Configuration](#configuration)
- [Output Format](#output-format)

---

## Quick Start

### Bootstrap (Initial 30K Paper Corpus)

```bash
export NCBI_API_KEY="your_key"          # Recommended (3x faster)
export NCBI_EMAIL="you@example.com"
export UNPAYWALL_EMAIL="you@example.com"

python -m agents.ingest.get_papers.pipeline \
  --mode bootstrap \
  --target 30000 \
  --fulltext-concurrency 8
```

**Runtime**: ~10 hours with API key, ~30 hours without  
**Output**: 30,000 papers (85-90% full-text coverage)

### Monthly Updates (Incremental)

```bash
# Run once per month (uses watermark)
python -m agents.ingest.get_papers.pipeline --mode monthly --target 2000
```

**Runtime**: ~2-3 hours  
**Output**: ~800-1,200 new papers (stable monthly growth)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: MULTI-SUPPLEMENT PUBMED SEARCH                         │
│                                                                  │
│  63 supplement-specific queries → PubMed E-utilities API        │
│  • Dynamic chunking (bypasses 10K limit)                        │
│  • Retry logic (3 attempts, exponential backoff)                │
│  • Proactive sub-chunking (checks count before pulling)         │
│                                                                  │
│  Output: ~190,000 PMIDs                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: PARSE & SCORE (Rule-Based)                            │
│                                                                  │
│  For each PMID (batches of 50):                                 │
│  • Fetch XML (efetch API)                                       │
│  • Parse: title, abstract, journal, year, study type            │
│  • Tag supplements (keyword matching)                            │
│  • Calculate reliability score (0-20+ points)                   │
│  • Infer primary goal (strength, endurance, etc.)               │
│                                                                  │
│  Output: ~125,000 human studies (animal/in-vitro filtered)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2.5: MONTHLY QUALITY FILTER (monthly mode only)          │
│                                                                  │
│  Three-tier system:                                             │
│  Tier 1: Always add (meta-analyses, exceptional, top N recent)  │
│  Tier 2: Per-supplement threshold check (hard-coded)            │
│  Tier 3: Reject (below all thresholds)                          │
│                                                                  │
│  Per-supplement evaluation:                                     │
│  • Small supplements (<100): P25 threshold, top 2/month         │
│  • Large supplements (≥100): Median threshold, top 10/month     │
│  • Multi-supplement papers: Qualify via lowest threshold        │
│  • Filter supplement tags: Remove tags that don't qualify       │
│                                                                  │
│  Bootstrap: Skipped                                             │
│  Monthly: ~4,000 → ~1,000 papers                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: QUALITY FILTER                                         │
│                                                                  │
│  Remove papers below threshold:                                 │
│  • Bootstrap: 2.0 minimum (balanced)                            │
│  • Monthly: 2.0 minimum (after monthly filter already applied)  │
│                                                                  │
│  Protected quotas (enhanced system):                            │
│  • Top 10 overall per supplement (by reliability score)         │
│  • Top 2 per supplement×goal combination                        │
│  • Full-text preference as tiebreaker                           │
│  • ~715 papers protected (added back if filtered)               │
│                                                                  │
│  Output: ~69,000 quality papers (bootstrap)                     │
│          ~900 quality papers (monthly)                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: DIVERSITY SELECTION                                    │
│                                                                  │
│  Iterative elimination to reach target (30k):                   │
│  • Score each supplement-goal combination                        │
│  • Eliminate worst combinations iteratively                      │
│  • Protected quotas never eliminated                             │
│  • 0.8 tiebreak threshold: prefer full-text when scores close   │
│                                                                  │
│  Ensures balanced representation across:                         │
│  • Supplements (creatine, caffeine, protein, etc.)              │
│  • Goals (strength, endurance, weight_loss, etc.)               │
│  • Study types (meta-analysis, RCT, etc.)                       │
│                                                                  │
│  Output: 30,000 selected papers (bootstrap)                     │
│          ~800-1,200 papers (monthly)                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: SAVE SELECTION                                         │
│                                                                  │
│  Write to: data/ingest/runs/<timestamp>/pm_papers.jsonl        │
│  Metadata: data/ingest/runs/<timestamp>/metadata.json          │
│  Pointer: data/ingest/runs/latest.json                         │
│  Watermark: data/ingest/watermark.json (for monthly)           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: FULL-TEXT FETCHING (default ON)                       │
│                                                                  │
│  Concurrent async fetching (8 workers):                         │
│                                                                  │
│  For each of 30k papers:                                        │
│    1. PMC Check (PubMed → PMC linking)                         │
│       ├─ PMC full text found (~22k, 73%)                       │
│       │  ├─ Has body sections → Extract + Save                 │
│       │  └─ Abstract-only → Mark for Unpaywall                 │
│       └─ Not in PMC (~8k, 27%) → Mark for Unpaywall            │
│                                                                  │
│    2. Unpaywall Rescue (for PMC abstract-only + not-in-PMC)    │
│       ├─ PDF found → Extract + Save (~5-6k rescued, 60-75%)    │
│       └─ Not available → Use abstract fallback                 │
│                                                                  │
│  Quality detection: Regex for body sections (INTRO, METHODS)    │
│  Content extraction: Title, abstract, body, tables, figures     │
│  Storage: data/fulltext_store (sharded, deduplicated)          │
│                                                                  │
│  Final coverage: 27-28k full texts (90%+), 2-3k abstracts (10%)│
│  Manifest: data/ingest/runs/<timestamp>/fulltext_manifest.json │
└─────────────────────────────────────────────────────────────────┘
```

---

## Reliability Scoring

### Scoring Components (0-20+ points)

Every paper receives an objective quality score based on:

#### 1. Study Type (1-12 pts)
| Type | Points | Rationale |
|------|--------|-----------|
| Meta-analysis | 12 | Highest evidence level |
| Systematic review | 11 | Comprehensive synthesis |
| Randomized controlled trial (RCT) | 10 | Gold standard |
| Crossover trial | 7 | Good control |
| Cohort study | 4 | Observational |
| Other | 1 | Minimal weight |

#### 2. Sample Size (0-5 pts)
| N | Points |
|---|--------|
| ≥1000 | 5 |
| ≥500 | 4 |
| ≥100 | 3 |
| ≥50 | 2 |
| ≥20 | 1 |
| <20 | 0 |

#### 3. Quality Indicators (0-8+ pts)
+1 pt for each keyword found:
- "systematic review", "meta-analysis"
- "double-blind", "placebo-controlled"
- "randomized", "controlled trial"
- "crossover", "longitudinal"

#### 4. Journal Impact (0-2 pts)
+2 pts for high-impact sports nutrition journals:
- Journal of the International Society of Sports Nutrition
- Sports Medicine
- Medicine & Science in Sports & Exercise
- British Journal of Sports Medicine
- International Journal of Sport Nutrition and Exercise Metabolism

#### 5. Recency (0-1 pt)
- Published 2020+: +1 pt

#### 6. Diversity Adjustment (±3 pts)
- Under-represented supplement: +3 pts
- Over-represented supplement: -3 pts

**Total Range**: 0-25+ points  
**Typical Distribution**:
- Meta-analyses: 12-20 pts
- High-quality RCTs: 10-18 pts
- Standard RCTs: 6-12 pts
- Observational: 3-8 pts

---

## Selection Pipeline

### Bootstrap Mode (Comprehensive)

**Target**: 30,000 papers  
**Quality Floor**: 2.0 (never compromised)  
**Strategy**: Maximum diversity across all dimensions

**Selection Algorithm:**

1. **Quality Filter**: Remove all papers < 2.0
   - Input: ~125K papers
   - Output: ~69K papers (55% pass rate)

2. **Enhanced Quota Protection**:
   - Top 10 overall per supplement (by reliability score)
   - Top 2 per supplement×goal combination
   - Full-text preference as tiebreaker
   - ~715 papers protected

3. **Diversity Filtering**:
   - Score each supplement-goal combination
   - Iteratively eliminate worst combinations
   - Protected quotas never eliminated
   - 0.8 tiebreak threshold: prefer full-text when scores within 0.8
   - Continues until target reached (30K)

**Output Distribution:**
- Balanced across supplements (no single supplement >10%)
- Balanced across goals (strength, endurance, etc.)
- Quality-preserved (all papers ≥2.0)
- Full-text preferred (within quality constraints)

### Monthly Mode (Incremental)

**Target**: ~2,000 papers (filtered to ~800-1,200)  
**Strategy**: Quality-aware additions using fixed thresholds

**Selection Algorithm:**

1. **Watermark-Based Fetch**:
   - Read `data/ingest/watermark.json`
   - Fetch papers published since last run (mindate = watermark - 1 day)
   - Input: ~4,000 new papers

2. **Monthly Quality Filter** (NEW STEP):
   - Load hard-coded thresholds from `monthly_thresholds.py`
   - Evaluate each paper against each supplement tag
   - Three-tier system:
     - Tier 1: Always add (meta-analyses, exceptional quality ≥4.5, top N recent)
     - Tier 2: Check against per-supplement threshold
     - Tier 3: Reject if below all thresholds
   - Filter supplement tags (keep only qualified tags)
   - Output: ~1,000 papers

3. **Normal Pipeline**:
   - Quality filter (2.0)
   - Enhanced quotas
   - Diversity selection
   - Output: ~800-1,200 papers

4. **Update Watermark**:
   - Save current timestamp for next month

---

## Monthly Update System

### Threshold Strategy

**Hard-coded, never changes** - provides stable, predictable behavior.

#### Small Corpora (<100 papers)
- **Threshold**: P25 (25th percentile)
- **Recency**: Top **2** most recent per month
- **Rationale**: Build diversity, avoid outlier drag

**Examples:**
```
raspberry-ketone (3 papers):  Threshold 1.75
ecdysteroids (3 papers):      Threshold 2.50
synephrine (23 papers):       Threshold 3.50
betaine (95 papers):          Threshold 4.50
```

#### Large Corpora (≥100 papers)
- **Threshold**: Median (50th percentile)
- **Recency**: Top **10** most recent per month
- **Rationale**: Maintain quality without over-restricting

**Examples:**
```
caffeine (1,016 papers):      Threshold 4.00
creatine (1,628 papers):      Threshold 4.00
vitamin-d (1,825 papers):     Threshold 5.00
beta-alanine (150 papers):    Threshold 4.50
```

**See `monthly_thresholds.py` for complete list (80 supplements)**

### Three-Tier Evaluation

#### Tier 1: Always Add
Papers that bypass thresholds:
- Meta-analyses
- Systematic reviews
- Exceptional quality (≥4.5)
- Top N most recent per supplement (if quality ≥2.5)

#### Tier 2: Threshold Check
Per-supplement evaluation:
```python
for each supplement tag:
    if paper.quality >= threshold[supplement]:
        keep tag
    else:
        remove tag

if has any qualifying tags:
    include paper with filtered tags
else:
    reject paper
```

#### Tier 3: Reject
Papers below threshold for ALL tags.

### Multi-Supplement Example

**Paper**: Quality 3.8, Tags: `caffeine, raspberry-ketone, protein`

| Supplement | Threshold | 3.8 ≥ Threshold? | Keep Tag? |
|------------|-----------|------------------|-----------|
| caffeine | 4.0 | ❌ No | Remove |
| raspberry-ketone | 1.75 | ✅ Yes | Keep |
| protein | 4.0 | ❌ No | Remove |

**Result**: Paper included with tags `raspberry-ketone` only

**Benefit**: Builds weak supplement corpora without diluting strong ones

### Recency Guarantee

Ensures fresh research is always included:

| Supplement Category | Paper Count | Top N/Month | Min Quality |
|---------------------|-------------|-------------|-------------|
| **Small** | <100 | 2 | 2.5 |
| **Large** | ≥100 (500+) | 10 | 2.5 |

**Large supplements:**
- arginine, caffeine, creatine, iron, magnesium, nitrate, omega-3, protein, vitamin-d

**Why**: Keeps corpus fresh with latest research even if quality standards haven't caught up.

### Expected Growth

**Month 1**: ~800-1,200 papers added  
**Month 6+**: ~800-1,200 papers added (stable, no decline)

**Why stable?** Fixed thresholds mean predictable, consistent monthly additions.

---

## Full-Text Fetching

### Dual-Source Strategy

```
For each paper (concurrent, async):
  
  1. PMC Check (PubMed → PMC linking via elink)
     ├─ Success: Fetch PMC XML
     │   ├─ Has body sections (INTRO, METHODS, etc.) → Full text
     │   └─ Abstract-only in XML → Mark for Unpaywall rescue
     └─ Not in PMC → Mark for Unpaywall rescue
  
  2. Unpaywall Rescue (for PMC failures & abstract-only)
     ├─ Query Unpaywall API by DOI
     ├─ Download best OA content (PDF or HTML)
     ├─ Extract text:
     │   ├─ PDF: PyPDF extraction
     │   └─ HTML: Trafilatura (article-aware) + BeautifulSoup fallback
     ├─ Quality check: Has body sections?
     │   ├─ Yes → Full text (upgrades PMC abstract-only)
     │   └─ No → Abstract-only
     └─ Not available → Keep PubMed abstract
  
  3. Save to Centralized Store (Smart Caching)
     ├─ Shard by key (2-level hex: pmid_xxx or doi_xxx)
     ├─ Store: {pmid, doi, fulltext_text, sources{pmc, unpaywall}, has_body_sections}
     ├─ Smart skip: Only skip if file exists AND has fulltext
     │   ├─ Has fulltext → Skip (resume-safe)
     │   └─ Abstract-only → Re-fetch to attempt upgrade
     └─ Include skipped files in manifest (complete database state)
```

### Coverage Statistics

**Typical results for 30K papers:**

| Source | Full Texts | Abstract-Only | Total |
|--------|------------|---------------|-------|
| PMC | ~20,000 (67%) | ~4,000 (13%) | 23,800 available |
| Unpaywall PDF | +5,000 | ~700 | ~5,700 attempted |
| Unpaywall HTML | +300-400 | ~50 | ~350-450 attempted |
| Not Available | - | ~6,200 (21%) | 6,200 |
| **Final** | **~25,300-25,400 (84-85%)** | **~4,600-4,700 (15-16%)** | **30,000** |

**Note**: Unpaywall rescues ~5,300-5,400 papers that PMC couldn't provide with fulltext.

### Quality Detection

**Full text vs abstract-only** determined by regex matching for body sections:
```python
BODY_SECTION_PATTERNS = [
    r'\b(INTRODUCTION|BACKGROUND)\b',
    r'\b(METHODS?|METHODOLOGY|MATERIALS? AND METHODS?)\b',
    r'\b(RESULTS?)\b',
    r'\b(DISCUSSION)\b',
    r'\b(CONCLUSION)\b'
]

has_body = any(pattern found in text)
```

### Storage Format

**Centralized sharded store**: `data/fulltext_store/`

```
data/fulltext_store/
├── 3a/
│   └── 7f/
│       └── pmid_12345678.json
└── e2/
    └── 4c/
        └── doi_10_1234_example.json
```

**Record schema:**
```json
{
  "pmid": "12345678",
  "doi": "10.1234/example",
  "abstract": "Paper abstract from PubMed...",
  "fulltext_text": "Full extracted text (or null if only abstract)...",
  "sources": {
    "pmc": {
      "pmcid": "PMC1234567",
      "status": "ok_efetch",
      "has_body_sections": true,
      "fulltext_bytes": 125000
    },
    "unpaywall": {
      "url": "https://...",
      "format": "pdf",
      "status": "ok_pdf",
      "has_body_sections": true,
      "content_bytes": 250000
    }
  }
}
```

### Manifest Statistics

The `fulltext_manifest.json` provides comprehensive statistics about the **complete database state** (not just newly fetched papers):

**Database State** (all papers in store):
```json
{
  "total": 30000,                      // All papers in database
  "pmc_total": 23834,                  // Papers available in PMC
  "pmc_full_text": 19957,              // PMC papers with fulltext
  "pmc_abstract_only": 3877,           // PMC papers with abstract only
  "unpaywall_total": 1050,             // Papers where Unpaywall attempted
  "unpaywall_full_text": 392,          // Unpaywall papers with fulltext
  "unpaywall_rescued": 250,            // PMC abstract-only → Unpaywall fulltext
  "full_text_with_body": 25300,        // Total papers with fulltext (PMC + Unpaywall)
  "full_text_percent": 84.33,          // Fulltext coverage
  "abstract_only_final": 4700          // Papers with only abstract available
}
```

**Run Operations** (this fetch run only):
```json
{
  "saved": 5200,                       // New files written
  "skipped_existing": 24800,           // Files already in database
  "skipped_with_fulltext": 23500,      // Skipped files that have fulltext
  "new_fulltext_fetched": 4100,        // New fulltexts acquired this run
  "attempted_upgrades": 1100           // Abstract-only files re-fetched
}
```

**Key insight**: When re-running fulltext fetch:
- Papers with fulltext are **skipped** (fast, no re-fetch)
- Papers with only abstract are **re-attempted** (upgrade opportunity)
- All papers (skipped + new) appear in manifest stats (complete database view)

### Performance

**With NCBI API key** (recommended):
- PMC: ~10 requests/sec (NCBI rate limit)
- Unpaywall: ~5 requests/sec (polite rate limiting)
- **Total time**: ~3-4 hours for 30K papers

**Without API key**:
- PMC: ~3 requests/sec (NCBI rate limit)
- **Total time**: ~10-12 hours for 30K papers

---

## Configuration

### Environment Variables

#### Required
```bash
NCBI_EMAIL="you@example.com"
```

#### Highly Recommended
```bash
NCBI_API_KEY="your_key"              # 3x faster PMC fetching
UNPAYWALL_EMAIL="you@example.com"    # Required for Unpaywall rescue
```

#### Optional
```bash
# Search & Selection
INGEST_LIMIT=30000                   # Target paper count
QUALITY_FLOOR_BOOTSTRAP=2.0          # Minimum quality (bootstrap)
QUALITY_FLOOR_MONTHLY=2.0            # Minimum quality (monthly, after monthly filter)
DIVERSITY_ROUNDS_THRESHOLD=30000     # When to use diversity filtering

# Enhanced Quotas
USE_ENHANCED_QUOTAS=true             # Enable enhanced quota system
MIN_OVERALL_PER_SUPPLEMENT=10        # Top N overall per supplement
MIN_PER_SUPPLEMENT_GOAL=2            # Top N per supplement×goal

# Full-Text Fetching
ENABLE_UNPAYWALL=true                # Enable Unpaywall rescue
FULLTEXT_STORE_DIR="data/fulltext_store"  # Centralized storage location
FULLTEXT_MAX_RETRIES=3               # HTTP retry count
FULLTEXT_TIMEOUT=30                  # HTTP timeout (seconds)
```

### Command-Line Arguments

```bash
--mode {bootstrap,monthly}          # Run mode
--target N                          # Target paper count
--fulltext-concurrency N            # Concurrent full-text workers (default: 8)
--no-fetch-fulltext                 # Disable full-text fetching
--dry_report N                      # Preview selection (no save)
```

---

## Output Format

### pm_papers.jsonl

Each line is a JSON object:

```json
{
  "id": "unique_id",
  "pmid": "12345678",
  "doi": "10.1234/example",
  "title": "Study title",
  "journal": "Journal Name",
  "year": 2024,
  "content": "Abstract or full text...",
  "url_pub": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  
  "study_type": "randomized_controlled_trial",
  "supplements": "creatine,protein",
  "primary_goal": "strength",
  "reliability_score": 12.5,
  
  "has_fulltext": true,
  "fulltext_source": "pmc",
  "fulltext_path": "data/fulltext_store/3a/7f/pmid_12345678.json",
  
  "_removed_supplements": ["caffeine"],  # Monthly mode only
  "_removal_reasons": {                  # Monthly mode only
    "caffeine": "below_threshold_4.00"
  },
  "_recency_guaranteed_for": ["creatine"]  # Monthly mode only
}
```

### metadata.json

```json
{
  "run_id": "20251006_135215",
  "mode": "bootstrap",
  "started_at": "2025-10-06T13:52:15Z",
  "completed_at": "2025-10-06T23:47:32Z",
  "duration_hours": 9.9,
  
  "pmids_fetched": 191234,
  "papers_parsed": 126543,
  "papers_after_quality_filter": 68921,
  "papers_selected": 30000,
  
  "quality_floor_bootstrap": 2.0,
  "enhanced_quotas_used": true,
  "protected_quota_count": 715,
  
  "fulltext_attempted": 30000,
  "fulltext_coverage": {
    "pmc_full_text": 22134,
    "pmc_abstract_only": 7866,
    "unpaywall_rescued": 5432,
    "full_text_total": 27566,
    "abstract_only_final": 2434,
    "coverage_percent": 91.9
  }
}
```

---

## Troubleshooting

### 429 Rate Limit (Too Many Requests)

**Symptoms**: `PubMed rate limit hit` or `429 Too Many Requests`

**Solutions:**
1. Get NCBI API key (increases limit from 3/sec to 10/sec)
2. Reduce `--fulltext-concurrency` (e.g., 4 instead of 8)
3. Wait for retry (auto-retries with exponential backoff: 5s, 10s, 15s)

### Timeout Errors

**Symptoms**: `The read operation timed out`

**Solution**: Automatic retry (3 attempts) - no action needed

### Low Full-Text Coverage

**Expected**: 85-90% full-text coverage

**If lower (<80%)**:
- Check UNPAYWALL_EMAIL is set
- Verify network connectivity
- Check `fulltext_manifest.json` for error details

### Missing Papers After Timeout

**System handles automatically:**
- 3 retries with exponential backoff
- Continues to next batch (doesn't lose remaining papers)
- Reports failed batches in logs

---

## See Also

- **[Main Ingest README](../README.md)** - User guide and monthly workflow
- **[paper_processor](../paper_processor/README.md)** - GPU processing stage
- **[Project README](../../../README.md)** - Overall EvidentFit architecture

