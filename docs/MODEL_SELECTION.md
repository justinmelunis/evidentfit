# Model Selection Strategy

## Overview

EvidentFit uses **GPT-4o-mini (Azure AI Foundry)** for all LLM tasks:

- **Cloud LLMs (GPT-4o-mini)**: All agentic tasks (banking, paper processing, summarization, API responses)
- **Legacy**: Mistral-7B local GPU available for paper processing but not recommended

This architecture provides **consistent quality**, **fast processing**, and **reasonable costs** across all components.

---

## Model Selection by Use Case

| Use Case | Model | Location | Why |
|----------|-------|----------|-----|
| **User API Responses** | GPT-4o-mini | Azure AI Foundry | Low latency, high quality, affordable at scale |
| **Evidence Banking** | GPT-4o-mini | Azure AI Foundry | Consistent with API, fast parallel execution, low cost |
| **Paper Processing** | GPT-4o-mini | Azure AI Foundry | Fast processing (2-3 hours vs 5 days), better quality, reasonable cost (~$39/year) |
| **Summarization** | GPT-4o-mini | Azure AI Foundry | Consistent quality across all components |

---

## GPT-4o-mini for User-Facing Applications

### Use Cases
1. **Real-Time Research Chat** (`/stream` endpoint)
   - User asks questions about supplements
   - System retrieves relevant papers
   - GPT-4o-mini synthesizes evidence into personalized answers
   
2. **Stack Recommendations** (`/stack/conversational` endpoint)
   - User provides profile (goal, weight, age, etc.)
   - System generates personalized supplement stack
   - GPT-4o-mini creates reasoning and explanations

3. **Evidence Banking** (pre-computed, runs quarterly)
   - Pre-computes evidence grades for 378 goal×supplement combinations (6 goals × 63 supplements)
   - Generates profile-specific reasoning for 17,010 combinations (270 profiles × 63 supplements)
   - Creates structured output with citations

### Why GPT-4o-mini?

#### ✅ **Performance**
- **Low latency**: 200-500ms response times
- **Parallel execution**: 100+ concurrent requests
- **Reliable**: 99.9% uptime SLA

#### ✅ **Cost Efficiency**
- **User API**: $0.15/1M input tokens, $0.60/1M output tokens
- **Typical query**: ~5k input + 500 output = **$0.001 per response**
- **Banking run**: ~50M input + 5M output = **~$10.50 per run** (with 63 supplements)
- **Annual cost**: ~$42/year (quarterly banking) + minimal API usage

#### ✅ **Quality**
- **Excellent reasoning**: Handles multi-document synthesis well
- **Citation accuracy**: Reliably references retrieved papers
- **Structured output**: Follows complex prompt instructions
- **Consistent**: Deterministic outputs with temperature=0

#### ✅ **Operational Benefits**
- **No infrastructure**: Fully managed by Azure
- **Scalable**: Auto-scales with demand
- **Integrated**: Works seamlessly with Azure Container Apps
- **Monitored**: Built-in logging and metrics

---

## Cost Analysis: Banking (Quarterly Updates)

We evaluated three options for evidence banking (pre-computing 378 evidence grades + 17,010 profile reasoning sets):

### Model Comparison

| Metric | **Llama-3.1-8B** (Local) | **GPT-4o-mini** ⭐ | **GPT-4o** |
|--------|--------------------------|-------------------|------------|
| **Per Run Cost** | $0.50 (electricity) | ~$10.50 | ~$175.00 |
| **Annual Cost** (4× runs) | $2.00 | **~$42.00** | ~$700.00 |
| **Runtime** | 8-12 hours | 20-30 minutes | 20-30 minutes |
| **Quality** | ~85-90% of GPT-4o-mini | Excellent (baseline) | ~5-10% better |
| **Setup Effort** | 2-4 hours | None (ready) | None (ready) |
| **Parallelization** | Limited (sequential) | Excellent (100+ concurrent) | Excellent |

### Token Usage Breakdown (63 supplements)
- **Level 1**: 378 calls × 6.5k input + 600 output = 2.46M input + 0.23M output
- **Level 2**: 17,010 calls × 2.5k input + 250 output = 42.5M input + 4.25M output
- **Total**: ~45M input tokens + ~4.5M output tokens per run

### Decision: GPT-4o-mini (Final Choice)

**GPT-4o-mini is our long-term model choice for banking.** After comprehensive evaluation, we've determined it provides the optimal balance of cost, quality, and speed for evidence grading tasks.

**Why we chose GPT-4o-mini over local models:**

1. **~$42/year is reasonable** for health-related evidence quality (with 63 supplements)
2. **60× faster** (30 min vs 10 hours) enables rapid iteration
3. **Already implemented and proven** - zero migration risk
4. **Consistent quality** across banking and API responses
5. **Parallelization** - process all 17,388 calls concurrently
6. **Developer time > $40/year savings** vs local model (still worth cloud for speed)
7. **Production-ready** - validated for health recommendations

**Why we rejected GPT-4o:**

- **17× more expensive** (~$700/year vs ~$42/year with 63 supplements)
- **Minimal quality gain** (~5-10% better) for structured evidence grading
- Premium reasoning not needed for this task
- Quality gain doesn't justify 17× cost increase

**Why we rejected local models (Mistral-7B/Llama-3.1-8B):**

- **Saves only ~$42/year** vs GPT-4o-mini (with 63 supplements)
- **60× slower** impacts development velocity (8-12 hours vs 30 min)
- **Quality validation overhead** (need to verify outputs)
- **Higher citation risk** - could hallucinate paper citations
- **~10-15% quality degradation** - unacceptable for health recommendations
- **Implementation effort** not justified for $42 savings given speed/quality trade-offs

---

## Paper Processing (GPT-4o-mini)

### Use Case: Research Paper Analysis
- **Initial run**: Process 30,000+ research papers from PubMed
- **Monthly updates**: Process 1-2K new papers per month
- Extract structured summaries for RAG ingestion
- Generate study design scores, outcome measures, dosing details
- Batch job (not user-facing, but benefits from faster processing)

### Model: GPT-4o-mini (Azure AI Foundry) - **Current Choice**

**Why GPT-4o-mini for paper processing?**

#### ✅ **Cost Efficiency**
- **Initial run (30K papers)**: ~$24.30 (one-time)
- **Monthly (1-2K papers)**: ~$0.81-1.62 per run
- **Annual cost**: ~$39/year (initial + 12 monthly runs at 1.5K papers/month average)
- **Very reasonable** for the quality and speed benefits

#### ✅ **Performance Benefits**
- **60× faster**: 2-3 hours vs 5 days (parallel execution)
- **Better quality**: 5-10% improvement in JSON compliance and extraction accuracy
- **More reliable**: 99.9% uptime, automatic retries
- **No infrastructure**: Fully managed cloud service

#### ✅ **Operational Benefits**
- **Faster iteration**: 2-3 hours enables rapid testing and improvements
- **Better for monthly updates**: 1-2K papers processed in 10-20 minutes
- **Consistent quality**: Same model used across all agents
- **No GPU maintenance**: Eliminates GPU infrastructure overhead

**Legacy Option**: Mistral-7B local GPU available via `PAPER_PROCESSOR_USE_CLOUD=0`, but not recommended due to speed and quality trade-offs.

**See [Paper Processor Model Comparison](PAPER_PROCESSOR_MODEL_COMPARISON.md)** for detailed analysis.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│  USER-FACING (Cloud - GPT-4o-mini)                  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │  Research Chat API              │                │
│  │  • Real-time responses          │                │
│  │  • Low latency (<500ms)         │                │
│  │  • ~$0.001 per query            │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │  Stack Recommendations          │                │
│  │  • Personalized reasoning       │                │
│  │  • Safety screening             │                │
│  │  • ~$0.002 per stack            │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │  Evidence Banking               │                │
│  │  • Quarterly updates            │                │
│  │  • Parallel execution (30 min)  │                │
│  │  • ~$10.50 per run (63 supps)   │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  Annual Cost: ~$42 + minimal API usage              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  BATCH PROCESSING (Cloud - GPT-4o-mini)             │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │  Paper Processor                │                │
│  │  • 30K papers initial           │                │
│  │  • 1-2K papers monthly          │                │
│  │  • GPT-4o-mini (Azure Foundry)  │                │
│  │  • Parallel execution           │                │
│  │  • ~2-3 hours (30K), ~10-20 min (1-2K) │         │
│  └─────────────────────────────────┘                │
│                                                      │
│  Cost: ~$24.30 initial + ~$1.22/month (~$39/year)   │
│  Legacy: Mistral-7B local GPU available but not recommended │
└─────────────────────────────────────────────────────┘
```

---

## Design Philosophy

### Cloud for Real-Time, Local for Batch

**Cloud LLMs (GPT-4o-mini) when:**
- ✅ User-facing, latency-sensitive
- ✅ Low/moderate volume
- ✅ Need 99.9% uptime
- ✅ Want zero infrastructure management
- ✅ Cost is proportional to value delivered

**Local GPU (Mistral-7B) when:**
- ✅ Batch processing, not latency-sensitive
- ✅ High volume (10K+ documents)
- ✅ Infrequent runs (monthly/quarterly)
- ✅ Cost savings > infrastructure complexity
- ✅ Privacy/control benefits

---

## Consistency Benefits

Using **GPT-4o-mini for both banking and API** provides:

1. **Consistent reasoning quality** across pre-computed and real-time responses
2. **Same citation style** in banking cache and user answers
3. **Predictable outputs** for testing and validation
4. **Simplified operations** - one model to monitor/optimize
5. **Unified prompt engineering** - learnings transfer across use cases

---

## Future Considerations

**Note**: We've evaluated alternatives and committed to GPT-4o-mini as our long-term choice. The scenarios below are only for extreme circumstances.

### When to Revisit Local Models for Banking

Consider switching to local models only if:
- Banking runs become **weekly or more frequent** (cost scales to ~$550+/year with 63 supplements)
- Privacy/compliance absolutely requires on-premise processing
- GPU infrastructure costs are already amortized (already have RTX 3080 for paper processing)
- **Extensive quality validation** confirms local model meets strict standards (90%+ grade agreement, <5% citation errors)
- **Note**: With 63 supplements, the cost savings (~$42/year) are minimal compared to quality/risk trade-offs

**See [Mistral vs GPT-4o-mini Banking Comparison](MISTRAL_VS_GPT4OMINI_BANKING.md)** for detailed performance analysis, risk assessment, and validation strategy.

**Current Status**: We are committed to GPT-4o-mini and have no plans to switch to local models given the minimal cost savings and quality/risk trade-offs.

### When to Upgrade to GPT-4o

Consider upgrading to GPT-4o (full version) if:
- User feedback indicates reasoning quality issues with GPT-4o-mini
- Complex multi-hop reasoning becomes core feature
- Budget allows (~$700/year for banking with 63 supplements + higher API costs)
- Premium quality justifies 17× cost increase
- You need better handling of edge cases (B/C grade assignments)

**GPT-4o vs GPT-4o-mini for Banking:**
- **Quality gain**: ~5-10% better (more nuanced reasoning, better edge case handling)
- **Cost increase**: ~17× ($700/year vs ~$42/year with 63 supplements)
- **Best for**: When you need premium quality and can justify the cost
- **Not recommended**: For structured evidence grading where mini already performs well

### Other Model Options (Not Recommended)

**Claude Sonnet/Gemini/Grok:**
- **Not available in Azure AI Foundry** (would require multi-cloud setup)
- **Inconsistency**: Different model for banking vs API responses
- **Operational complexity**: Multiple API keys, different error handling
- **Recommendation**: Stick with Azure AI Foundry ecosystem

**Newer Models (GPT-4.1 Nano, o4-mini, etc.):**
- **Availability**: Many are experimental or not yet in Azure AI Foundry
- **Stability**: Unproven for production use
- **Recommendation**: Wait for official Azure integration and proven track record

---

## Environment Variables

### Cloud LLMs (Azure AI Foundry)
```bash
FOUNDATION_ENDPOINT=https://your-project.openai.azure.com
FOUNDATION_KEY=your_api_key
FOUNDATION_API_VERSION=2024-05-01-preview
FOUNDATION_CHAT_MODEL=gpt-4o-mini
FOUNDATION_EMBED_MODEL=text-embedding-3-small
```

### Local GPU (Paper Processor)
```bash
# No API keys needed - runs on local GPU
CUDA_VISIBLE_DEVICES=0  # RTX 3080
MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.3
```

---

## Monitoring & Costs

### Production Monitoring
- **API latency**: Track p50, p95, p99 response times
- **Token usage**: Monitor input/output tokens per request
- **Error rates**: Alert on 4xx/5xx responses
- **Cost tracking**: Daily spend alerts via Azure Cost Management

### Expected Monthly Costs (63 supplements + monthly paper processing)
- **Banking**: ~$10.50 × 0.33 runs = **~$3.50/month** (quarterly)
- **Paper Processing**: ~$1.22/month (1-2K papers monthly)
- **API usage**: ~$10-50/month (depends on traffic)
- **Total**: **~$15-55/month** for all cloud LLM usage

---

## References

- [Azure AI Foundry Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
- [GPT-4o-mini Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#gpt-4o-mini)
- [Paper Processor Architecture](../agents/ingest/paper_processor/README.md)
- [Banking System Documentation](../agents/banking/README.md)

