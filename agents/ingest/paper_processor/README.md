# Paper Processor - GPU-Accelerated Research Analysis

GPU-accelerated structured analysis of research papers using Mistral-7B, optimized for processing 30K+ papers with streaming I/O and smart chunking.

## Overview

The paper processor transforms raw research papers into structured, Q&A-ready summaries using local GPU inference. It handles full-text papers (from PMC), intelligently chunks content that exceeds context limits, and uses two-pass extraction to ensure complete, high-quality outputs.

## Key Features

### Memory & Performance
- **Streaming architecture**: Process 30K+ papers without RAM limits
- **Smart chunking**: Automatically splits long full-text papers at natural boundaries
- **Resume capability**: Pick up where you left off after interruptions
- **VRAM optimized**: 4-bit quantization + Flash Attention 2 + bfloat16 (6-8GB usage)

### Quality & Accuracy
- **Two-pass extraction**: Initial strict prompt + targeted repair for missing fields
- **One-shot prompting**: Example-driven outputs for consistent structure
- **Schema validation**: Ensures all required fields are present
- **Deterministic sampling**: Temperature=0 for stable, reproducible outputs

### Integration
- **Automatic input**: Reads from `get_papers` latest pointer
- **Full-text ready**: Handles both full texts and abstracts seamlessly
- **Structured output**: Q&A-focused JSON with evidence grades, key findings, dosing details

## Quick Start

### Requirements
- **GPU**: NVIDIA with 10GB+ VRAM (RTX 3080 recommended)
- **RAM**: 16GB+ (32GB recommended for 30K dataset)
- **Python**: 3.9+
- **CUDA**: 11.8+ with PyTorch

### Installation

```bash
cd agents/ingest/paper_processor

# Install dependencies
pip install -r requirements.txt

# Install PyTorch with CUDA support
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

### Basic Usage

```bash
# Process papers from latest get_papers run
python -m agents.ingest.paper_processor.run \
  --max-papers 30000 \
  --batch-size 1 \
  --model mistralai/Mistral-7B-Instruct-v0.3
```

### Resume Interrupted Run

```bash
# If processing was interrupted, resume from the .tmp file
python -m agents.ingest.paper_processor.run \
  --max-papers 30000 \
  --resume-summaries data/paper_processor/summaries/summaries_20251006_123456.jsonl.tmp
```

### Process Specific Run

```bash
# Process a specific JSONL file
python -m agents.ingest.paper_processor.run \
  --papers-jsonl data/ingest/runs/20251005_172726/pm_papers.jsonl \
  --max-papers 30000
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT: pm_papers.jsonl from get_papers                      │
│ (Papers with full text when available, abstracts as fallback)│
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STREAMING READER                                            │
│ • Streams papers one-at-a-time (low RAM)                    │
│ • Loads seen dedupe keys for resume                         │
│ • Skip already-processed papers                             │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ SMART CHUNKING                                              │
│ • Calculate safe character budget (context - output - prompt)│
│ • Split at paragraph boundaries (prefer \n\n)               │
│ • Fall back to sentence boundaries (. )                     │
│ • Preserve semantic coherence                               │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ TWO-PASS LLM EXTRACTION (Mistral-7B)                       │
│                                                              │
│ Pass 1: Strict Initial Extraction                          │
│ • One-shot example-driven prompt                            │
│ • Minified JSON skeleton                                    │
│ • Temperature=0 (deterministic)                             │
│ • Output: Structured summary (may have gaps)                │
│                                                              │
│ Pass 2: Targeted Repair (if needed)                        │
│ • Detect missing/empty fields                               │
│ • Small repair prompt (256 tokens)                          │
│ • Fill only missing fields                                  │
│ • Merge with initial output                                 │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ CHUNK MERGING                                               │
│ • Union list fields (key_findings, supplements, etc.)       │
│ • Keep first chunk's scalar fields                          │
│ • De-duplicate while preserving order                       │
│ • Normalize and validate                                    │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STREAMING WRITER                                            │
│ • Write summaries incrementally (low RAM)                   │
│ • Atomic finalization (.tmp → .jsonl)                       │
│ • Aggregate stats on-the-fly                                │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ OUTPUT                                                       │
│ • summaries_<timestamp>.jsonl (structured summaries)        │
│ • stats_<timestamp>.json (processing metrics)               │
│ • latest.json (pointer to most recent run)                  │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Command-Line Arguments

```bash
--papers-jsonl PATH       # Input JSONL (default: latest from get_papers)
--max-papers N            # Max papers to process (default: 200)
--batch-size N            # Keep at 1 to cap VRAM (default: 1)
--ctx-tokens N            # Model context window (default: 16384)
--max-new-tokens N        # Max output tokens (default: 640)
--model NAME              # Model to use (default: mistralai/Mistral-7B-Instruct-v0.3)
--resume-summaries PATH   # Resume from .jsonl or .jsonl.tmp file
```

### Environment Variables

```bash
# Optional: Enable Flash Attention 2 (if installed)
export EF_ATTN_IMPL="flash_attention_2"  # Significant speedup

# Model settings
export PP_MODEL="mistralai/Mistral-7B-Instruct-v0.3"
export PP_CTX_TOKENS=16384
export PP_MAX_NEW_TOKENS=640

# Batch settings (keep low for VRAM)
export PP_BATCH=1
```

## Output Schema

Each summary includes:

```json
{
  "id": "pmid_12345678",
  "pmid": "12345678",
  "doi": "10.1234/example",
  "title": "Study Title",
  "journal": "Journal Name",
  "year": 2024,
  
  "summary": "2-5 sentence overview",
  "key_findings": ["Finding 1", "Finding 2", ...],
  "supplements": ["creatine", "protein"],
  "evidence_grade": "A",
  "quality_score": 4.2,
  
  "study_type": "randomized_controlled_trial",
  "study_design": "double-blind, placebo-controlled",
  "population": {
    "age_range": "18-35",
    "sex": "mixed",
    "training_status": "trained",
    "sample_size": 150
  },
  
  "dosage": {
    "maintenance": "5g/day",
    "timing": "post-workout",
    "form": "monohydrate"
  },
  
  "outcome_measures": {
    "strength": ["1RM bench press", "1RM squat"],
    "endurance": [],
    "power": ["vertical jump"]
  },
  
  "keywords": ["creatine", "strength", "RCT"],
  "relevance_tags": ["performance", "resistance_training"],
  "limitations": ["Short duration", "Homogeneous population"],
  
  "dedupe_key": "pmid_12345678",
  "schema_version": "v1.2"
}
```

## Performance

### RTX 3080 Benchmarks

| Papers | Processing Time | Rate | VRAM Usage |
|--------|----------------|------|------------|
| 1,000  | ~4 hours       | 4-5 papers/min | 6-8GB |
| 10,000 | ~40 hours      | 4-5 papers/min | 6-8GB |
| 30,000 | ~5 days        | 4-5 papers/min | 6-8GB |

### Optimizations

- **4-bit quantization**: Reduces VRAM by 75% (16GB → 4GB model)
- **Flash Attention 2**: 2-3x faster inference (if available)
- **bfloat16**: Better numerical stability than float16
- **Streaming I/O**: No RAM spikes regardless of dataset size
- **GPU cache clearing**: Periodic cleanup prevents fragmentation

### Cost Comparison

**💸 Local Model vs. Cloud API**

Processing ~30,000 research papers (≈300 million tokens):

| Approach | Est. Cost per Run | Ongoing Monthly | Notes |
|----------|-------------------|-----------------|-------|
| **Local GPU (Mistral-7B)** | $0 (hardware only) | $0 | RTX 3080, ~5 days |
| **Azure GPT-4o-mini API** | ~$900 – $1,800 | ~$30 – $70 | Cheaper but less capable |
| **Azure GPT-4o API (premium)** | ~$22,500+ | ~$700+ | Premium quality |

## Storage

```
data/paper_processor/
├── summaries/
│   ├── summaries_20251006_123456.jsonl     # Structured outputs
│   └── summaries_20251006_123456.jsonl.tmp # In-progress (resume from this)
├── stats/
│   └── stats_20251006_123456.json          # Processing metrics
└── latest.json                              # Pointer to most recent run

logs/paper_processor/
└── paper_processor.log                      # Rotating file logger
```

## Telemetry & Stats

The processor tracks comprehensive metrics:

```json
{
  "run_id": "paper_processor_1733512345",
  "papers_in": 30000,
  "papers_out": 28543,
  "skipped_empty": 892,
  "skipped_dedup": 565,
  "coverage_ratio": 0.951,
  
  "chunks_total": 42180,
  "avg_chunks_per_doc": 1.48,
  
  "elapsed_sec": 432180,
  "rate_papers_per_sec": 0.066,
  "median_latency_sec": 14.2,
  
  "model": "mistralai/Mistral-7B-Instruct-v0.3",
  "ctx_tokens": 16384,
  "max_new_tokens": 640,
  
  "index_stats": {
    "total_papers": 28543,
    "study_types": {"meta-analysis": 1245, "RCT": 8932, ...},
    "evidence_grades": {"A": 5432, "B": 9821, "C": 8234, "D": 5056},
    "supplements": {"creatine": 2134, "protein": 1876, ...}
  }
}
```

## Troubleshooting

### CUDA Out of Memory

**Problem**: GPU runs out of VRAM

**Solutions**:
- Ensure `--batch-size 1` (default)
- Check no other GPU processes running
- Model should use ~6-8GB with 4-bit quant
- Reduce `--ctx-tokens` if still issues

### Slow Processing

**Expected**: ~4-5 papers/minute on RTX 3080

**If slower**:
- Install Flash Attention 2 for 2-3x speedup
- Check GPU utilization (should be 90-100%)
- Ensure CUDA drivers up to date
- Verify using GPU: check logs for "device: cuda"

### Empty Summaries

**Problem**: Model outputs invalid JSON

**Handled automatically**:
- First-pass failure → Minimal fallback stub
- Missing fields → Second-pass repair
- Still incomplete → Valid defaults filled
- Never discards papers

### Resume Not Working

**Problem**: Can't resume interrupted run

**Check**:
- Use exact path to `.jsonl.tmp` file
- File must exist and be readable
- Dedupe keys loaded from partial file
- Processing continues from where it stopped

## Advanced Usage

### Custom Model

```bash
# Use different Mistral variant
python -m agents.ingest.paper_processor.run \
  --model mistralai/Mistral-7B-Instruct-v0.2 \
  --max-papers 30000
```

### Parallel Processing

```bash
# Split dataset and process in parallel (advanced)
# Paper 1-15000
python -m agents.ingest.paper_processor.run \
  --max-papers 15000 \
  --papers-jsonl data/ingest/runs/latest/pm_papers.jsonl

# Paper 15001-30000 (separate terminal)
# Use --resume-summaries with different portion of input
```

### Integration with Banking

After processing, use summaries for evidence banking:

```bash
cd agents/banking
python level1_banking.py  # Uses processed summaries
```

## Dependencies

Key packages from `requirements.txt`:

```
torch>=2.1.0              # PyTorch with CUDA
transformers>=4.41.0      # Hugging Face models
accelerate>=0.33.0        # Model loading
bitsandbytes>=0.43.0      # 4-bit quantization (Linux/WSL)
```

## See Also

- **[get_papers README](../get_papers/README.md)** - Paper selection and full-text fetching
- **[Main Agent README](../README.md)** - Overall architecture
- **[Project README](../../../README.md)** - Full system documentation
