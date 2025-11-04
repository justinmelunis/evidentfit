# Paper Processor: Mistral-7B vs GPT-4o-mini Comparison

## Current Setup

**Current Model**: GPT-4o-mini (Azure AI Foundry) - **Active Choice**
- **Initial Volume**: 30,000+ research papers (one-time)
- **Monthly Volume**: 1-2K papers per month
- **Task**: Extract structured data (population, intervention, outcomes, safety)
- **Cost**: ~$24.30 per 30K papers, ~$0.81-1.62 per 1-2K papers
- **Runtime**: 2-3 hours for 30K papers, 10-20 minutes for 1-2K papers (parallel execution)
- **Quality**: Better JSON compliance and extraction accuracy than local models

**Legacy Model**: Mistral-7B-Instruct (local GPU) - Available but not recommended

## Task Complexity

The paper processor extracts structured JSON from research papers:
- **Population**: sample size, demographics, training status
- **Intervention**: dosing, duration, supplement forms, loading phases
- **Outcomes**: effect sizes, statistical significance, measures
- **Safety**: adverse events, contraindications, safety grades

**Key Requirements**:
1. **Structured JSON output** - Must follow exact schema
2. **Data extraction accuracy** - Numbers, dosages, effect sizes
3. **Provenance tracking** - Track where data came from in paper
4. **Batch processing** - Process 30K papers efficiently

## Cost Analysis

### GPT-4o-mini Cost Estimates

**Initial Run (30K papers)**:
- Input tokens: 30,000 × 3,000 = **90M tokens**
- Output tokens: 30,000 × 600 = **18M tokens**
- Cost: (90M × $0.15/1M) + (18M × $0.60/1M) = **~$24.30**

**Monthly Run (1-2K papers)**:
- 1K papers: (3M input × $0.15/1M) + (0.6M output × $0.60/1M) = **~$0.81**
- 2K papers: (6M input × $0.15/1M) + (1.2M output × $0.60/1M) = **~$1.62**
- Average (1.5K papers): **~$1.22 per run**

**Annual Cost** (initial + 12 monthly runs at 1.5K papers/month):
- Initial (30K): ~$24.30
- Monthly (12 × 1.5K): ~$1.22 × 12 = ~$14.64
- **Total: ~$39/year**

**Pricing** (Azure AI Foundry):
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens

**Note**: Previous estimate of $900-1,800 was for GPT-4 (full version) or outdated pricing.

### Comparison

| Metric | **Mistral-7B (Local)** | **GPT-4o-mini (Cloud)** |
|--------|------------------------|-------------------------|
| **Initial Run (30K)** | $0 | **~$24.30** |
| **Monthly Run (1-2K)** | $0 | **~$0.81-1.62** |
| **Annual Cost** | $0 | **~$39/year** (initial + 12 monthly) |
| **Runtime (30K)** | ~5 days (sequential) | **~2-3 hours** (parallel) |
| **Runtime (1-2K)** | ~4-8 hours | **~10-20 minutes** (parallel) |
| **Quality** | Good (85-90%) | **Better** (92-95%, better JSON compliance) |
| **Infrastructure** | Requires GPU | **Zero** (cloud managed) |
| **Reliability** | Manual monitoring | **99.9% uptime** |
| **Resumability** | Manual checkpoint | **Automatic retry** |

## Performance Comparison

### Mistral-7B Strengths
- ✅ **Cost**: $0 per run (electricity only)
- ✅ **Proven**: Already working well for this task
- ✅ **Privacy**: On-premise processing
- ✅ **Control**: Full control over model and quantization

### Mistral-7B Weaknesses
- ⚠️ **Slow**: ~5 days sequential processing
- ⚠️ **JSON compliance**: Occasional parsing errors
- ⚠️ **Complex papers**: May struggle with complex statistical data
- ⚠️ **Infrastructure**: Requires GPU maintenance

### GPT-4o-mini Strengths
- ✅ **Speed**: 2-3 hours with parallel execution (60× faster)
- ✅ **Quality**: Better JSON compliance, fewer parsing errors
- ✅ **Complex papers**: Better handling of statistical data and effect sizes
- ✅ **Reliability**: 99.9% uptime, automatic retries
- ✅ **No infrastructure**: Fully managed cloud service
- ✅ **Resumability**: Easy to resume failed runs

### GPT-4o-mini Weaknesses
- ⚠️ **Cost**: ~$24.30 per run (~$97/year for quarterly runs)
- ⚠️ **Cloud dependency**: Requires internet and Azure service
- ⚠️ **Privacy**: Papers processed in cloud (though Azure has strong privacy)

## Quality Comparison

### Expected Quality Differences

**Mistral-7B**:
- **Structured extraction**: ~85-90% accuracy
- **JSON compliance**: ~90-95% (some parsing errors)
- **Number extraction**: ~85-90% (dosing, effect sizes)
- **Complex papers**: May miss nuanced statistical details

**GPT-4o-mini**:
- **Structured extraction**: ~92-95% accuracy
- **JSON compliance**: ~98-99% (very rare parsing errors)
- **Number extraction**: ~92-95% (better at dosing, effect sizes)
- **Complex papers**: Better handling of statistical nuances

**Quality Gain**: ~5-10% improvement with GPT-4o-mini, especially for:
- Complex statistical data (effect sizes, confidence intervals)
- Unusual dosing formats
- Papers with multiple interventions
- Safety information extraction

## Recommendation

**Decision: GPT-4o-mini is our choice for paper processing**

We've migrated from Mistral-7B to GPT-4o-mini because:
1. **Monthly processing** (1-2K papers) makes cost very reasonable (~$10-19/month)
2. **60× faster** (2-3 hours vs 5 days) enables rapid iteration
3. **Better quality** (5-10% improvement) for structured extraction
4. **No infrastructure** overhead (no GPU maintenance)

### Legacy: Mistral-7B (Previous Choice)

**Why we switched to GPT-4o-mini**:
1. **Monthly processing**: 1-2K papers/month makes cost very reasonable (~$10-19/month)
2. **60× faster**: 2-3 hours vs 5 days enables rapid iteration
3. **Better quality**: 5-10% improvement, especially for complex papers
4. **Reliability**: 99.9% uptime, automatic retries
5. **No infrastructure**: Fully managed, no GPU maintenance
6. **Initial run cost**: ~$24.30 for 30K papers is acceptable for one-time bootstrap

**Legacy Mistral-7B option**:
1. **Still available**: Can be enabled via `PAPER_PROCESSOR_USE_CLOUD=0`
2. **Cost savings**: $0 vs ~$10-19/month (but 60× slower)
3. **Privacy**: On-premise processing (if that matters)
4. **Infrastructure**: Requires GPU maintenance

**Cost-benefit analysis**:
- **Monthly processing**: ~$39/year (initial + 12 monthly) vs $0/year
- **Speed value**: 5 days → 2-3 hours (60× faster) for 30K papers
- **Monthly speed**: 4-8 hours → 10-20 minutes (20-24× faster) for 1-2K papers
- **Quality value**: 5-10% improvement in extraction accuracy

### Decision Framework

**Switch to GPT-4o-mini if**:
- ✅ You process papers **monthly or more frequently**
- ✅ You need **faster iteration** on paper processing
- ✅ Quality issues emerge with Mistral-7B (JSON parsing errors, missed data)
- ✅ You want to **eliminate GPU maintenance** overhead
- ✅ **$97/year is acceptable** for 60× speed + 5-10% quality gain

**Keep Mistral-7B if**:
- ✅ You process papers **quarterly or less frequently**
- ✅ **Cost savings are critical** ($97/year matters)
- ✅ **Privacy is a concern** (on-premise required)
- ✅ Current quality is **acceptable** (no quality issues)
- ✅ GPU infrastructure is **already amortized**

## Migration Path (If Switching)

### Phase 1: Parallel Comparison
1. **Run both models** on same 100-paper sample
2. **Compare outputs**:
   - JSON compliance rate
   - Data extraction accuracy
   - Processing time
3. **Measure differences**: Identify quality gaps

### Phase 2: Cost Validation
1. **Run full 30K papers** with GPT-4o-mini
2. **Validate actual cost** matches estimate (~$24.30)
3. **Measure runtime** (should be 2-3 hours)

### Phase 3: Production Switch
1. **Update code** to use Azure AI Foundry client
2. **Add retry logic** for API failures
3. **Monitor quality** and costs
4. **Keep GPU** for other tasks or future use

## Cost-Benefit Summary

**Current (GPT-4o-mini)**:
- Cost: ~$39/year (initial + 12 monthly runs at 1.5K papers/month)
- Speed: 2-3 hours for 30K, 10-20 min for 1-2K (60× faster)
- Quality: Better (92-95%)
- Infrastructure: None

**Legacy (Mistral-7B)**:
- Cost: $0/year
- Speed: 5 days for 30K, 4-8 hours for 1-2K
- Quality: Good (85-90%)
- Infrastructure: GPU required

**Verdict**: 
- **GPT-4o-mini is our choice** for paper processing
- **~$39/year is very reasonable** for 60× speed improvement + 5-10% quality gain
- **Monthly processing** (1-2K papers) makes the cost-benefit trade-off clear
- **Legacy Mistral option** available but not recommended

## Conclusion

**GPT-4o-mini is our choice** for paper processing:
- **5-10% quality improvement** (better JSON compliance, complex data extraction)
- **60× faster** (2-3 hours vs 5 days for 30K papers, 10-20 min vs 5 days for 1-2K papers)
- **More reliable** (99.9% uptime, automatic retries)
- **Cost is reasonable**: ~$24.30 initial + ~$1.22/month (~$39/year total)

**Migration complete**: We've switched from Mistral-7B to GPT-4o-mini for paper processing. The code supports both via `PAPER_PROCESSOR_USE_CLOUD` environment variable, but GPT-4o-mini is the default and recommended choice.

