# EvidentFit Ingest Agent (Agent A)

## Overview

The EvidentFit Ingest Agent is responsible for discovering, scoring, selecting, and indexing high-quality research papers from PubMed into Azure AI Search. It implements a sophisticated **multi-query strategy** with **iterative diversity filtering** to maintain a diverse, high-quality dataset of approximately 12,000 papers optimized for supplement research.

## Core Objectives

1. **Quality First**: Prioritize meta-analyses, RCTs, and well-designed studies over lower-quality research
2. **Diversity**: Ensure balanced representation across supplements, training goals, populations, study types, and journals
3. **Storage Optimization**: Maintain a curated dataset that fits within Azure AI Search free tier constraints (50 MB)
4. **Continuous Improvement**: Support both bootstrap (initial) and monthly (incremental) update modes
5. **Rate Limit Compliance**: Respect PubMed API limits with intelligent retry logic and delays

## Architecture

### Data Flow

```
Multi-Query PubMed Search (30 supplements)
    ↓ [Date-based chunking to bypass 10K limit]
XML Parsing & Metadata Extraction
    ↓ [Parse Articles]
Phase 1: Reliability Scoring (4.0 threshold)
    ↓ [Quality Filter - ~60,000 papers]
Phase 2: Iterative Diversity Filtering
    ↓ [Dynamic Selection - 12,000 papers]
Azure AI Search Index
    ↓ [Upsert Documents]
Watermark Update
```

### Two Operating Modes

#### **Bootstrap Mode**
- Initial population of the index
- Multi-query search across 30 supplements from 1990-01-01 to present
- Collects ~124,000 PMIDs, processes ~95,000 papers
- Applies 4.0 quality threshold, selects best 12,000 papers
- Uses iterative diversity filtering for optimal balance

#### **Monthly Mode**
- Incremental updates based on watermark
- Fetches only papers published since last run
- Integrates new papers with existing dataset
- Re-applies iterative diversity filtering to maintain diversity

## Scoring Methodology

### Phase 1: Reliability Scoring (0-20+ points)

Every paper receives a **reliability score** based on objective quality indicators. This is a lightweight, reproducible heuristic designed to rank papers without requiring manual review or API lookups.

#### 1. Study Type Score (1-12 points)
- **Meta-analysis**: +12 points — highest evidence level, synthesis of multiple studies
- **RCT (Randomized Controlled Trial)**: +10 points — gold standard for interventions
- **Crossover**: +7 points — good control design, within-subject comparison
- **Cohort**: +4 points — observational but useful for long-term outcomes
- **Other**: +1 point — baseline for published work

#### 2. Sample Size Score (0-5 points)
Extracted via regex patterns from abstract (e.g., "n=50", "100 participants"):
- **≥1000 participants**: +5 points (very large, high statistical power)
- **≥500**: +4 points (large study)
- **≥100**: +3 points (medium study)
- **≥50**: +2 points (small study)
- **≥20**: +1 point (pilot/feasibility)
- **<20 or not detected**: 0 points

*Note: Regex may under/over-count if abstract formatting is atypical; treated as a signal, not a gate.*

#### 3. Quality Indicators (0-8+ points)
Each keyword detected in the title adds +1 point:
- "systematic review"
- "meta-analysis"
- "double-blind"
- "placebo-controlled"
- "randomized"
- "controlled trial"
- "crossover"
- "longitudinal"

*Papers can accumulate multiple indicators (e.g., a "randomized, double-blind, placebo-controlled trial" gets +4).*

#### 4. Journal Impact (0-2 points)
Simple heuristic based on curated list of sports nutrition/physiology journals:
- **High-impact**: +2 points for journals like:
  - J Appl Physiol, Med Sci Sports Exerc, J Strength Cond Res
  - Sports Med, Am J Clin Nutr, Nutrients, J Int Soc Sports Nutr
  - Eur J Appl Physiol, Int J Sport Nutr Exerc Metab
- **Other journals**: 0 points (not penalized, just no bonus)

*This is a small nudge, not a gate. Can be expanded or removed as needed.*

#### 5. Recency Score (0-1 points)
- **2020 or later**: +1 point (recent findings)
- **2015-2019**: +0.5 points (still relatively recent)
- **Before 2015**: 0 points (older papers still valuable, just not prioritized)

#### 6. Diversity Bonus (±3 points)
To prevent the corpus from being overwhelmed by creatine papers, we apply small adjustments:
- **Under-represented supplements**: +3 to +0.5 points
  - Rare: tribulus, D-aspartic acid, deer antler, ecdysteroids (+3)
  - Medium-rare: betaine, taurine, carnitine, ZMA (+2.5-2.0)
  - Less common: citrulline, nitrate, beta-alanine (+1.0-0.5)
- **Over-represented supplements**: -1 point
  - Creatine (most common) gets small penalty to make room for diversity

*This is overridden by dynamic weights when combination-aware scoring is active.*

**Typical Score Range**: 0-20+ points (most papers fall in 5-15 range)

**Quality Threshold**: Papers must score ≥4.0 points to proceed to Phase 2 (filters out cohorts and other low-quality papers, keeps RCTs and crossovers).

### Phase 2: Iterative Diversity Filtering

After reliability scoring, papers are processed through **iterative diversity filtering** to ensure balanced representation across multiple dimensions simultaneously. This prevents the corpus from being dominated by a few over-studied combinations (e.g., "creatine + strength + trained athletes + RCT").

#### Tracked Combinations

The system analyzes existing papers and new candidates across five combination types:

1. **supplement × goal** (e.g., "creatine_strength", "beta-alanine_endurance")
2. **supplement × population** (e.g., "creatine_trained-athletes", "nitrate_older-adults")
3. **goal × population** (e.g., "hypertrophy_untrained", "weight_loss_clinical")
4. **study_type × goal** (e.g., "meta-analysis_strength", "RCT_weight_loss")
5. **journal × supplement** (e.g., "sports-med_creatine", "nutrients_beta-alanine")

#### Iterative Elimination Process

The system uses **iterative diversity filtering** with 1,000-paper elimination rounds:

**Process**:
1. **Initial Set**: Start with all quality-filtered papers (~60,000)
2. **Round 1**: Calculate combination weights, eliminate lowest 1,000 papers
3. **Round 2**: Recalculate weights, eliminate next 1,000 papers
4. **Continue**: Repeat until target count (12,000) is reached
5. **Final Selection**: Best 12,000 papers with optimal diversity

**Weight Calculation** (recalculated each round):
- **Target percentage**: 1% per combination for large corpus
- **Over-represented** (>3× target): **-2.0** penalty
- **Well-represented** (>2× target): **-1.0** penalty
- **Adequately represented** (>1× target): **0.0** neutral
- **Under-represented** (0.5-1× target): **+1.5** bonus
- **Severely under-represented** (<0.5× target): **+3.0** bonus

*This iterative approach provides better diversity outcomes than single-pass selection.*

#### Paper-Level Combination Score

For each paper, the system:
1. Identifies all combinations the paper belongs to (typically 5-10 combinations)
2. Sums the weights across all matching combinations
3. Applies **quality safeguards**:
   - Papers with reliability <5.0 can only get **max +30% of base score** as combination bonus
   - This prevents weak papers from being selected purely for diversity
4. Returns the adjusted combination score (typically -10 to +15 range)

**Example**:
- Paper: Creatine RCT in trained athletes for strength
- Combinations:
  - creatine_strength: -2.0 (over-represented)
  - creatine_trained-athletes: -1.0 (well-represented)
  - strength_trained-athletes: -1.0 (well-represented)
  - RCT_strength: 0.0 (adequate)
  - sports-med_creatine: -2.0 (over-represented)
- **Combination score**: -6.0 (penalized for common combination)

#### Quality Safeguards

1. **Low-quality papers**: If reliability <5.0, positive combination bonus capped at 30% of base score
2. **Example**: Paper with reliability 4.0 and combination score +9.0 → capped at +1.2
3. **Rationale**: Diversity is important, but not at the expense of quality

### Final Enhanced Score

```
Enhanced Score = Reliability Score + Combination Score
```

**Typical Range**: 0-25 points
- Reliability: 0-20+ (most papers 5-15)
- Combination: -10 to +15 (typically -5 to +5)

**Example Scenarios**:
- **High-quality, common topic**: Reliability 15 + Combination -5 = **10** (solid but not prioritized)
- **High-quality, novel topic**: Reliability 15 + Combination +8 = **23** (highly prioritized)
- **Low-quality, novel topic**: Reliability 3 + Combination +8 → capped at 3 + 0.9 = **3.9** (filtered out)
- **High-quality meta-analysis**: Reliability 18 + Combination 0 = **18** (prioritized for quality alone)

## Paper Selection Process

### Bootstrap Mode Workflow

1. **Multi-Query Search**: Search 30 supplements individually, collect ~124,000 PMIDs
2. **Date Chunking**: Use date-based chunking to bypass PubMed 10K limit
3. **Parse & Extract**: Extract metadata, abstract, authors, journal, etc.
4. **Reliability Scoring**: Calculate objective quality scores for all papers
5. **Quality Filter**: Remove papers with reliability score <4.0 (~60,000 papers remain)
6. **Iterative Diversity Filtering**: Eliminate papers in 1,000-paper rounds
7. **Weight Recalculation**: Recalculate combination weights each round
8. **Final Selection**: Select best 12,000 papers with optimal diversity
9. **Upsert to Index**: Store selected papers in Azure AI Search
10. **Watermark Update**: Record latest publication date for monthly runs

### Monthly Mode Workflow

1. **Watermark Check**: Read last ingestion date from index
2. **PubMed Search**: Fetch new papers since watermark
3. **Parse & Score**: Apply full two-phase scoring to new papers
4. **Merge with Existing**: Combine new papers with existing index
5. **Re-score & Select**: Re-apply iterative diversity filtering to full dataset
6. **Maintain Limit**: Keep best 12,000 papers, remove lowest-scoring
7. **Upsert Changes**: Update index with new selection
8. **Update Watermark**: Record new last ingestion date

## Metadata Extraction

Each paper is enriched with extensive metadata for downstream processing:

### Core Fields
- `id`: Unique key (`pmid_XXXXXXXX_chunk_0`)
- `pmid`: PubMed ID
- `doi`: Digital Object Identifier
- `title`: Article title
- `journal`: Journal name
- `year`: Publication year
- `url_pub`: PubMed URL
- `content`: Abstract text (full text not stored due to size constraints)

### Study Classification
- `study_type`: meta-analysis | RCT | crossover | cohort | other
- `supplements`: Comma-separated list of supplements discussed
- `population`: Study population (e.g., "trained athletes", "untrained")

### Goal-Specific Outcomes
- `primary_goal`: Main training goal (strength | hypertrophy | endurance | weight_loss | general)
- `hypertrophy_outcomes`: Detected hypertrophy-related outcomes
- `weight_loss_outcomes`: Detected weight-loss outcomes
- `strength_outcomes`: Detected strength/power outcomes
- `performance_outcomes`: Detected performance outcomes

### Study Metadata
- `sample_size`: Number of participants
- `sample_size_category`: small | medium | large | very-large
- `study_duration`: Duration of intervention
- `duration_category`: acute | short | medium | long
- `population_category`: untrained | trained-athletes | older-adults | clinical | general

### Quality Indicators
- `study_design_score`: Double-blind, placebo-controlled, randomized indicators
- `has_loading_phase`: Boolean for supplement loading protocols
- `has_maintenance_phase`: Boolean for maintenance dosing
- `safety_indicators`: Adverse events, side effects, contraindications
- `has_side_effects`: Boolean
- `has_contraindications`: Boolean

### Authorship & Credibility
- `first_author`: First author name
- `author_count`: Number of authors
- `funding_sources`: Detected funding sources
- `mesh_terms`: MeSH (Medical Subject Headings) terms
- `keywords`: Author keywords

### Dosage Information
- `dosage_info`: Extracted dosing protocols (e.g., "5g/day", "loading protocol")

### Scoring Fields
- `reliability_score`: Phase 1 objective quality score (30-100)
- `combination_score`: Phase 2 diversity adjustment (-20 to +20)
- `enhanced_score`: Final selection score (10-120)

### Index Metadata
- `index_version`: Version tag (e.g., "v1-2025-09-25")
- `outcomes`: Legacy field for backward compatibility

## Multi-Query Strategy

### Supplement-Specific Queries

The system uses **30 individual supplement queries** instead of a single broad query to ensure comprehensive coverage:

```python
SUPPLEMENT_QUERIES = {
    # Core performance supplements
    "creatine": 'creatine AND (exercise OR training OR performance OR strength OR muscle) AND humans[MeSH]',
    "caffeine": 'caffeine AND (exercise OR training OR performance OR endurance OR strength) AND humans[MeSH]',
    "beta-alanine": '"beta-alanine" AND (exercise OR training OR performance OR muscle OR fatigue) AND humans[MeSH]',
    "protein": '"protein supplementation" AND (exercise OR training OR muscle OR hypertrophy OR strength) AND humans[MeSH]',
    
    # Nitric oxide boosters
    "citrulline": 'citrulline AND (exercise OR training OR performance) AND humans[MeSH]',
    "nitrate": '(nitrate OR beetroot) AND (exercise OR training OR performance OR endurance) AND humans[MeSH] NOT pollution',
    "arginine": 'arginine AND (exercise OR training OR performance) AND humans[MeSH]',
    
    # Amino acids and derivatives
    "hmb": 'HMB AND (exercise OR training OR muscle OR strength OR recovery) AND humans[MeSH]',
    "bcaa": 'BCAA AND (exercise OR training OR muscle OR recovery OR endurance) AND humans[MeSH]',
    "leucine": 'leucine AND (exercise OR training OR muscle) AND humans[MeSH]',
    "glutamine": 'glutamine AND (exercise OR training OR recovery OR muscle) AND humans[MeSH]',
    
    # Other performance compounds
    "betaine": 'betaine AND (exercise OR training OR performance OR strength OR power) AND humans[MeSH]',
    "taurine": 'taurine AND (exercise OR training OR performance OR endurance OR muscle) AND humans[MeSH]',
    "carnitine": 'carnitine AND (exercise OR training OR performance) AND humans[MeSH]',
    
    # Hormonal/anabolic
    "tribulus": 'tribulus AND (exercise OR training OR testosterone OR performance OR strength) AND humans[MeSH]',
    "d-aspartic-acid": '"d-aspartic acid" AND (exercise OR training OR testosterone OR performance) AND humans[MeSH]',
    
    # Essential nutrients
    "omega-3": 'omega-3 AND (exercise OR training OR performance OR recovery OR inflammation) AND humans[MeSH]',
    "vitamin-d": 'vitamin D AND (exercise OR training OR performance OR muscle OR strength) AND humans[MeSH]',
    "magnesium": 'magnesium AND (exercise OR training OR performance OR muscle OR recovery) AND humans[MeSH]',
    "iron": 'iron AND (exercise OR training OR performance OR endurance OR fatigue) AND humans[MeSH]',
    
    # Performance enhancers
    "sodium-bicarbonate": 'sodium bicarbonate AND (exercise OR training OR performance OR endurance) AND humans[MeSH]',
    "glycerol": 'glycerol AND (exercise OR training OR performance OR hydration) AND humans[MeSH]',
    
    # Antioxidants
    "curcumin": 'curcumin AND (exercise OR training OR performance OR recovery OR inflammation) AND humans[MeSH]',
    "quercetin": 'quercetin AND (exercise OR training OR performance OR recovery OR inflammation) AND humans[MeSH]',
    
    # Adaptogens
    "ashwagandha": 'ashwagandha AND (exercise OR training OR performance OR stress OR recovery) AND humans[MeSH]',
    "rhodiola": 'rhodiola AND (exercise OR training OR performance OR stress OR endurance) AND humans[MeSH]',
    "cordyceps": 'cordyceps AND (exercise OR training OR performance OR endurance) AND humans[MeSH]',
    
    # Amino acids
    "tyrosine": 'tyrosine AND (exercise OR training OR performance OR stress OR cognitive OR focus) AND humans[MeSH]',
    
    # Other
    "cla": 'CLA AND (exercise OR training OR performance OR weight OR fat) AND humans[MeSH]',
    "zma": 'ZMA AND (exercise OR training OR recovery OR sleep OR testosterone) AND humans[MeSH]'
}
```

### Date-Based Chunking

For supplements with >10,000 results, the system uses **date-based chunking** to bypass PubMed's 10K limit:

```python
def search_supplement_chunked(supplement: str, query: str, mindate: str) -> list:
    # Split search into date ranges
    # Chunk 1: 1990/01/01 to 2007/11/17
    # Chunk 2: 2007/11/18 to 2025/10/03
    # Each chunk gets up to 10,000 results
```

### Exclusions
- **Pollution studies**: Excludes NO₂ (nitrogen dioxide) environmental research
- **Animal studies**: Minimal filter (trusts PubMed MeSH filtering)
- **Non-English**: No explicit filter (PubMed tends toward English)

### API Rate Limiting
- **Batch size**: 50 papers per PubMed EFetch call
- **Delay**: 1.0 second between all requests (increased from 0.34s)
- **Retry logic**: 3 attempts with exponential backoff
- **429 Rate Limits**: 10s, 20s, 30s backoff for rate limit errors
- **NCBI API key**: Optional but recommended for higher rate limits

## Storage Optimization

### Why Abstract-Only?

To fit within Azure AI Search free tier (50 MB), we store:
- **Abstracts only** (typically 200-500 words)
- **No full text** (would require 10-100x more storage)
- **No embeddings** (free tier doesn't support vector search)

### Storage Calculations

- **Target**: 12,000 papers
- **Average abstract**: 2,000 characters (2 KB)
- **Metadata**: ~1 KB per paper
- **Total per paper**: ~3 KB
- **Total dataset**: 12,000 × 3 KB = 36 MB (fits in 50 MB limit with buffer)

### Future Scaling

For full-text storage and embeddings, consider:
- **PostgreSQL + pgvector**: Self-hosted, unlimited storage
- **Azure AI Search paid tier**: Vector search support
- **Hybrid approach**: Abstracts in Search, full text in blob storage

## Environment Variables

### Required
- `SEARCH_ENDPOINT`: Azure AI Search endpoint URL
- `SEARCH_ADMIN_KEY`: Azure AI Search admin key (for write access)
- `SEARCH_INDEX`: Index name (default: `evidentfit-index`)
- `FOUNDATION_ENDPOINT`: Azure AI Foundry endpoint (for embeddings, if enabled)
- `FOUNDATION_KEY`: Azure AI Foundry API key
- `NCBI_EMAIL`: Email for PubMed API (required by NCBI)

### Optional
- `NCBI_API_KEY`: NCBI API key for higher rate limits
- `INDEX_VERSION`: Version tag (default: `v1`)
- `INGEST_LIMIT`: Final paper count (default: 12000)
- `MAX_TEMP_LIMIT`: Temporary processing limit (default: 20000)
- `WATERMARK_KEY`: Watermark document ID (default: `meta:last_ingest`)
- `PM_SEARCH_QUERY`: Custom PubMed query (overrides default)
- `LOG_LEVEL`: Logging verbosity (default: info)

## Running the Agent

### Docker (Recommended)

```bash
docker build -t evidentfit-ingest .
docker run --env-file .env evidentfit-ingest bootstrap
```

### Local Development

```bash
# Install shared library
cd ../../shared
pip install -e .

# Return to ingest directory
cd ../agents/ingest

# Install dependencies
pip install -r requirements.txt

# Run bootstrap
python run.py bootstrap

# Run monthly update
python run.py monthly
```

### Azure Container Apps Job

```bash
# Deploy job
az containerapp job create \
  --name evidentfit-ingest-job \
  --resource-group evidentfit \
  --image justinmelunis/evidentfit-ingest:latest \
  --env-vars-file env.yaml \
  --trigger-type Manual

# Execute job
az containerapp job start --name evidentfit-ingest-job --resource-group evidentfit
```

## Performance & Timing

### Expected Runtimes

- **Bootstrap mode**: 25-40 minutes
  - Multi-query search: 10-15 minutes (~124,000 PMIDs)
  - Parsing & scoring: 10-15 minutes (~95,000 papers)
  - Iterative diversity filtering: 5-10 minutes
  - Index upsert: 5-10 minutes

- **Monthly mode**: 5-15 minutes
  - New papers: typically 100-500/month
  - Merge & re-score: 5-10 minutes
  - Index update: 1-3 minutes

### Bottlenecks

1. **PubMed API**: Rate limited; 1-second delays between requests to avoid 429 errors
2. **Parsing XML**: xmltodict can be slow for large responses
3. **Index upsert**: Azure AI Search has throughput limits on free tier
4. **Iterative filtering**: Recalculating weights each round is computationally intensive

## Error Handling

### PubMed API Errors

- **429 Too Many Requests**: 10s, 20s, 30s backoff with retry logic
- **500 Internal Server Error**: Retry up to 3 times, reduce batch size
- **JSON decode errors**: Strip invalid control characters and retry
- **XML parse errors**: Log and skip malformed articles
- **String responses**: Handle cases where PubMed returns strings instead of XML

### Azure AI Search Errors

- **400 Bad Request**: Check document format (no colons/pipes in IDs)
- **413 Payload Too Large**: Reduce upsert batch size
- **404 Index Not Found**: Run `ensure_index()` to create schema

### Data Quality Errors

- **Missing abstracts**: Skip papers without abstracts (can't assess quality)
- **Malformed dates**: Use fallback parsing or skip
- **Invalid PMIDs**: Log and skip

## Quality Assurance

### Post-Ingest Checks

1. **Count verification**: Confirm ~12,000 papers in index
2. **Supplement distribution**: Check representation across all 30 supplements
3. **Study type distribution**: Verify meta-analyses and RCTs are well-represented
4. **Recency**: Confirm recent papers (last 5 years) are included
5. **Watermark**: Verify watermark document was updated
6. **Quality threshold**: Verify 4.0 threshold filtered appropriately

### Monitoring Queries

```python
# Check total count
GET /indexes/evidentfit-index/docs/$count

# Check supplement distribution
POST /indexes/evidentfit-index/docs/search
{
  "search": "*",
  "facets": ["supplements"],
  "top": 0
}

# Check study type distribution
POST /indexes/evidentfit-index/docs/search
{
  "search": "*",
  "facets": ["study_type"],
  "top": 0
}
```

## Future Enhancements

### Planned Improvements

1. **Citation graph analysis**: Use citation networks to boost seminal papers
2. **Author reputation scoring**: Weight papers by author h-index
3. **Full-text extraction**: Move to paid tier or self-hosted for full papers
4. **Embeddings**: Enable semantic search (requires vector support)
5. **Duplicate detection**: Dedup by DOI, title similarity, or citation links
6. **Multi-language support**: Expand beyond English papers

### Alternative Architectures

1. **LangGraph + PostgreSQL**: Local indexing with pgvector for embeddings
2. **Elasticsearch**: Self-hosted alternative to Azure AI Search
3. **Pinecone/Weaviate**: Specialized vector databases for semantic search

## Troubleshooting

### Common Issues

**Problem**: Ingest fails with "SEARCH_ADMIN_KEY not found"
- **Solution**: Ensure `SEARCH_ADMIN_KEY` env var is set (not `SEARCH_QUERY_KEY`)

**Problem**: Papers not diverse (all creatine)
- **Solution**: Check `MAX_TEMP_LIMIT` is set high enough (≥20,000) to allow diversity analysis

**Problem**: PubMed 429 rate limit errors
- **Solution**: Increase delays in `pubmed_esearch()` and `pubmed_efetch_xml()` (currently 1.0s)

**Problem**: PubMed 500 errors
- **Solution**: Reduce batch size in `pubmed_efetch_xml()` (currently 50)

**Problem**: Only 3 documents in index
- **Solution**: Check Azure Container Apps job logs; likely a runtime error before upsert

**Problem**: Watermark not updating
- **Solution**: Verify `WATERMARK_KEY` uses underscores (e.g., `meta_last_ingest`), not colons

## License & Attribution

This agent is part of the EvidentFit project. Research papers are sourced from PubMed under NIH data usage policies. Always cite original sources when using paper metadata or abstracts.

## Contact

For questions or issues with the ingest agent, please open an issue in the EvidentFit repository.

