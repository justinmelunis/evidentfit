# EvidentFit Ingest Agent (Agent A)

## Overview

The EvidentFit Ingest Agent is responsible for discovering, scoring, selecting, and indexing high-quality research papers from PubMed into Azure AI Search. It implements a sophisticated **two-phase rolling window system** with **combination-aware dynamic scoring** to maintain a diverse, high-quality dataset of approximately 8,000 papers optimized for supplement research.

## Core Objectives

1. **Quality First**: Prioritize meta-analyses, RCTs, and well-designed studies over lower-quality research
2. **Diversity**: Ensure balanced representation across supplements, training goals, populations, study types, and journals
3. **Storage Optimization**: Maintain a curated dataset that fits within Azure AI Search free tier constraints (50 MB)
4. **Continuous Improvement**: Support both bootstrap (initial) and monthly (incremental) update modes

## Architecture

### Data Flow

```
PubMed (E-utilities API)
    ↓ [Search & Fetch]
XML Parsing & Metadata Extraction
    ↓ [Parse Articles]
Phase 1: Reliability Scoring
    ↓ [Quality Filter]
Phase 2: Combination-Aware Scoring
    ↓ [Dynamic Selection]
Azure AI Search Index
    ↓ [Upsert Documents]
Watermark Update
```

### Two Operating Modes

#### **Bootstrap Mode**
- Initial population of the index
- Fetches papers from 2000-01-01 to present
- Processes ~12,000 papers, selects best ~8,000
- Uses two-phase scoring for optimal diversity

#### **Monthly Mode**
- Incremental updates based on watermark
- Fetches only papers published since last run
- Integrates new papers with existing dataset
- Re-applies combination scoring to maintain diversity

## Scoring Methodology

### Phase 1: Reliability Scoring (0-20+ points)

Every paper receives a **reliability score** based on objective quality indicators. This is a lightweight, reproducible heuristic designed to rank papers without requiring manual review or API lookups.

#### 1. Study Type Score (2-10 points)
- **Meta-analysis**: +10 points — highest evidence level, synthesis of multiple studies
- **RCT (Randomized Controlled Trial)**: +8 points — gold standard for interventions
- **Crossover**: +6 points — good control design, within-subject comparison
- **Cohort**: +4 points — observational but useful for long-term outcomes
- **Other**: +2 points — baseline for published work

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

**Quality Threshold**: Papers must score ≥3.0 points to proceed to Phase 2 (filters out extremely low-quality or off-topic papers).

### Phase 2: Combination-Aware Scoring (variable adjustment)

After reliability scoring, papers are re-scored based on **diversity needs** to ensure balanced representation across multiple dimensions simultaneously. This prevents the corpus from being dominated by a few over-studied combinations (e.g., "creatine + strength + trained athletes + RCT").

#### Tracked Combinations

The system analyzes existing papers and new candidates across five combination types:

1. **supplement × goal** (e.g., "creatine_strength", "beta-alanine_endurance")
2. **supplement × population** (e.g., "creatine_trained-athletes", "nitrate_older-adults")
3. **goal × population** (e.g., "hypertrophy_untrained", "weight_loss_clinical")
4. **study_type × goal** (e.g., "meta-analysis_strength", "RCT_weight_loss")
5. **journal × supplement** (e.g., "sports-med_creatine", "nutrients_beta-alanine")

#### Dynamic Weights Calculation

The system samples up to 1,000 existing documents and calculates weights based on representation:

**Target percentage** (adaptive to corpus size):
- Small corpus (<100 papers): 10% per combination
- Medium corpus (100-1000): 5% per combination  
- Large corpus (≥1000): 1% per combination

**Weight assignment** based on current representation:
- **Severely over-represented** (>5× target): **-4.0** penalty
- **Over-represented** (>3× target): **-2.0** penalty
- **Well-represented** (>2× target): **-1.0** penalty
- **Adequately represented** (>1× target): **0.0** neutral
- **Under-represented** (0.5-1× target): **+1.5** bonus
- **Severely under-represented** (<0.5× target): **+3.0** bonus

*Combinations not yet in the corpus receive maximum bonus (+3.0) for introducing new coverage.*

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

1. **PubMed Search**: Fetch ~12,000 papers matching supplement/training query
2. **Parse & Extract**: Extract metadata, abstract, authors, journal, etc.
3. **Reliability Scoring**: Calculate objective quality scores for all papers
4. **Quality Filter**: Remove papers with reliability score <30
5. **Combination Analysis**: Analyze distribution across all combination dimensions
6. **Weight Calculation**: Calculate dynamic weights for underrepresented combinations
7. **Combination Scoring**: Re-score all papers with combination-aware weights
8. **Sort & Select**: Sort by enhanced score, select top 8,000 papers
9. **Upsert to Index**: Store selected papers in Azure AI Search
10. **Watermark Update**: Record latest publication date for monthly runs

### Monthly Mode Workflow

1. **Watermark Check**: Read last ingestion date from index
2. **PubMed Search**: Fetch new papers since watermark
3. **Parse & Score**: Apply full two-phase scoring to new papers
4. **Merge with Existing**: Combine new papers with existing index
5. **Re-score & Select**: Re-apply combination scoring to full dataset
6. **Maintain Limit**: Keep best 8,000 papers, remove lowest-scoring
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

## PubMed Query Strategy

### Base Query
```
(creatine OR "beta-alanine" OR caffeine OR citrulline OR nitrate OR 
 "nitric oxide" OR HMB OR "branched chain amino acids" OR BCAA OR 
 tribulus OR "d-aspartic acid" OR betaine OR taurine OR carnitine OR 
 ZMA OR glutamine OR CLA OR ecdysterone OR "deer antler")
AND
(resistance OR "strength" OR "1RM" OR hypertrophy OR "lean mass")
NOT
("nitrogen dioxide" OR NO2 OR pollution)
```

### Exclusions
- **Pollution studies**: Excludes NO₂ (nitrogen dioxide) environmental research
- **Animal studies**: No explicit filter (relies on PubMed defaults)
- **Non-English**: No explicit filter (PubMed tends toward English)

### API Rate Limiting
- **Batch size**: 50 papers per PubMed EFetch call
- **Delay**: 2-3 seconds between batches
- **Retry logic**: 3 attempts with exponential backoff on 500 errors
- **NCBI API key**: Optional but recommended for higher rate limits

## Storage Optimization

### Why Abstract-Only?

To fit within Azure AI Search free tier (50 MB), we store:
- **Abstracts only** (typically 200-500 words)
- **No full text** (would require 10-100x more storage)
- **No embeddings** (free tier doesn't support vector search)

### Storage Calculations

- **Target**: 8,000 papers
- **Average abstract**: 2,000 characters (2 KB)
- **Metadata**: ~1 KB per paper
- **Total per paper**: ~3 KB
- **Total dataset**: 8,000 × 3 KB = 24 MB (fits in 50 MB limit)

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
- `INGEST_LIMIT`: Final paper count (default: 8000)
- `MAX_TEMP_LIMIT`: Temporary processing limit (default: 12000)
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

- **Bootstrap mode**: 30-60 minutes
  - PubMed fetch: 10-15 minutes (~12,000 papers)
  - Parsing & scoring: 15-20 minutes
  - Combination analysis: 5-10 minutes
  - Index upsert: 5-10 minutes

- **Monthly mode**: 5-15 minutes
  - New papers: typically 100-500/month
  - Merge & re-score: 5-10 minutes
  - Index update: 1-3 minutes

### Bottlenecks

1. **PubMed API**: Rate limited; reduced batch size to 50 to avoid 500 errors
2. **Parsing XML**: xmltodict can be slow for large responses
3. **Index upsert**: Azure AI Search has throughput limits on free tier

## Error Handling

### PubMed API Errors

- **429 Too Many Requests**: Exponential backoff, increase delays
- **500 Internal Server Error**: Retry up to 3 times, reduce batch size
- **JSON decode errors**: Strip invalid control characters and retry
- **XML parse errors**: Log and skip malformed articles

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

1. **Count verification**: Confirm ~8,000 papers in index
2. **Supplement distribution**: Check representation across all supplements
3. **Study type distribution**: Verify meta-analyses and RCTs are well-represented
4. **Recency**: Confirm recent papers (last 5 years) are included
5. **Watermark**: Verify watermark document was updated

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
- **Solution**: Check `MAX_TEMP_LIMIT` is set high enough (≥12,000) to allow diversity analysis

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

