# Model Selection Strategy

## Overview

EvidentFit uses a **hybrid LLM approach** that balances cost, quality, and performance:

- **Cloud LLMs (GPT-4o-mini)**: User-facing API responses & evidence banking
- **Local GPU (Mistral-7B)**: Batch research paper processing

This architecture optimizes for both **production reliability** (cloud) and **cost efficiency** (local for batch jobs).

---

## Model Selection by Use Case

| Use Case | Model | Location | Why |
|----------|-------|----------|-----|
| **User API Responses** | GPT-4o-mini | Azure AI Foundry | Low latency, high quality, affordable at scale |
| **Evidence Banking** | GPT-4o-mini | Azure AI Foundry | Consistent with API, fast parallel execution, low cost |
| **Paper Processing** | Mistral-7B | Local GPU (RTX 3080) | Batch job, high volume, one-time cost |

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
   - Pre-computes evidence grades for 162 goal×supplement combinations
   - Generates profile-specific reasoning for 360 user profiles
   - Creates structured output with citations

### Why GPT-4o-mini?

#### ✅ **Performance**
- **Low latency**: 200-500ms response times
- **Parallel execution**: 100+ concurrent requests
- **Reliable**: 99.9% uptime SLA

#### ✅ **Cost Efficiency**
- **User API**: $0.15/1M input tokens, $0.60/1M output tokens
- **Typical query**: ~5k input + 500 output = **$0.001 per response**
- **Banking run**: 25M input + 2.5M output = **$5.32 per run**
- **Annual cost**: ~$21/year (quarterly banking) + minimal API usage

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

We evaluated three options for evidence banking (pre-computing 162 evidence grades + 360 profile reasoning sets):

### Model Comparison

| Metric | **Llama-3.1-8B** (Local) | **GPT-4o-mini** ⭐ | **GPT-4o** |
|--------|--------------------------|-------------------|------------|
| **Per Run Cost** | $0.50 (electricity) | $5.32 | $88.68 |
| **Annual Cost** (4× runs) | $2.00 | **$21.28** | $354.72 |
| **Runtime** | 8-12 hours | 20-30 minutes | 20-30 minutes |
| **Quality** | ~85-90% of GPT-4o-mini | Excellent (baseline) | ~5-10% better |
| **Setup Effort** | 2-4 hours | None (ready) | None (ready) |
| **Parallelization** | Limited (sequential) | Excellent (100+ concurrent) | Excellent |

### Token Usage Breakdown
- **Level 1**: 162 calls × 6.5k input + 600 output = 1.05M input + 0.097M output
- **Level 2**: 9,720 calls × 2.5k input + 250 output = 24.3M input + 2.43M output
- **Total**: ~25.35M input tokens + ~2.53M output tokens per run

### Decision: GPT-4o-mini

**Why we chose GPT-4o-mini over local models:**

1. **$21/year is negligible** for health-related evidence quality
2. **60× faster** (30 min vs 10 hours) enables rapid iteration
3. **Already implemented and proven** - zero migration risk
4. **Consistent quality** across banking and API responses
5. **Parallelization** - process all 9,882 calls concurrently
6. **Developer time > $19/year savings** vs local model

**Why we rejected GPT-4o:**

- **17× more expensive** ($354/year vs $21/year)
- **Minimal quality gain** for structured evidence grading
- Premium reasoning not needed for this task

**Why we rejected Llama-3.1-8B (local):**

- **Saves only $19/year** vs GPT-4o-mini
- **60× slower** impacts development velocity
- **Quality validation overhead** (need to verify outputs)
- **Implementation effort** not justified for $19 savings

---

## Local GPU for Paper Processing

### Use Case: Research Paper Analysis
- Process 30,000+ research papers from PubMed
- Extract structured summaries for RAG ingestion
- Generate study design scores, outcome measures, dosing details
- One-time batch job (not user-facing)

### Model: Mistral-7B-Instruct

**Why local GPU (vs cloud API)?**

#### ✅ **Cost Savings**
- **Cloud cost**: $900-1,800 per 30K-paper run
- **Local cost**: $0 (one-time GPU purchase, minimal electricity)
- **ROI**: GPU pays for itself in 1-2 runs

#### ✅ **Batch Job Characteristics**
- Not latency-sensitive (can run overnight)
- Infrequent (monthly or quarterly)
- High volume (30K papers × ~3K tokens each)
- Sequential processing acceptable

#### ✅ **Infrastructure Control**
- Full control over quantization and optimization
- Can pause/resume without API rate limits
- Can experiment with different models
- Privacy (papers processed on-premise)

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
│  │  • $5.32 per run                │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  Annual Cost: ~$21 + minimal API usage              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  BATCH PROCESSING (Local - Mistral-7B)              │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────────────────────┐                │
│  │  Paper Processor                │                │
│  │  • 30K papers per run           │                │
│  │  • GPU-accelerated (RTX 3080)   │                │
│  │  • 4-bit quantization + FA2     │                │
│  │  • Streaming architecture       │                │
│  │  • ~5 days runtime              │                │
│  └─────────────────────────────────┘                │
│                                                      │
│  Cost: $0 per run (one-time GPU investment)         │
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

### When to Revisit Local Models for Banking

Consider switching to local models if:
- Banking runs become **weekly** (cost scales to $276/year)
- Privacy/compliance requires on-premise processing
- GPU infrastructure costs are already amortized
- Quality validation confirms Llama-3.1-8B meets standards

### When to Upgrade to GPT-4o

Consider upgrading if:
- User feedback indicates reasoning quality issues
- Complex multi-hop reasoning becomes core feature
- Budget allows ($354/year for banking + higher API costs)
- Premium quality justifies 17× cost increase

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

### Expected Monthly Costs
- **Banking**: $5.32 × 0.33 runs = **$1.76/month** (quarterly)
- **API usage**: ~$10-50/month (depends on traffic)
- **Total**: **$12-52/month** for all cloud LLM usage

---

## References

- [Azure AI Foundry Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
- [GPT-4o-mini Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#gpt-4o-mini)
- [Paper Processor Architecture](../agents/ingest/paper_processor/README.md)
- [Banking System Documentation](../agents/banking/README.md)

