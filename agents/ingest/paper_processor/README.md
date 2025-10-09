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
- **Full-text first**: Uses full text when available; falls back to abstracts when needed; skips papers with neither
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

### Bootstrap Usage (Initial 30K Papers)

```bash
# Process papers from latest get_papers bootstrap run
python -m agents.ingest.paper_processor.run \
  --mode bootstrap \
  --max-papers 30000 \
  --batch-size 1 \
  --model mistralai/Mistral-7B-Instruct-v0.3

# Output: data/paper_processor/summaries/summaries_<timestamp>.jsonl
# This becomes your master summaries file for monthly updates
```

### Monthly Updates (Incremental Processing)

```bash
# Process only NEW papers from latest monthly get_papers run
python -m agents.ingest.paper_processor.run \
  --mode monthly \
  --master-summaries data/paper_processor/summaries/summaries_20251006_123456.jsonl \
  --max-papers 2000

# Automatically:
# ✓ Cross-run deduplication (skips already-processed papers)
# ✓ Appends to master summaries file (with backup)
# ✓ Saves monthly delta file (audit trail)
# ✓ Rebuilds and validates master index
# ✓ Detects abstract→fulltext upgrade candidates and saves a list for follow-up
```

### Resume Interrupted Run

```bash
# If processing was interrupted, resume from the .tmp file
# Note: latest pointer (data/paper_processor/latest.json) is refreshed periodically during runs
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

## Monthly Update System

### Architecture

The paper processor supports two modes optimized for different workflows:

**Bootstrap Mode** (Initial 30K papers):
- Processes entire corpus from scratch
- Outputs single summaries file
- No deduplication needed
- Duration: ~5 days on RTX 3080

**Monthly Mode** (Incremental updates):
- Loads master summaries for deduplication
- Processes only NEW papers (~800-1,200/month)
- Appends to master with auto-backup
- Saves monthly delta for audit trail
- Rebuilds master index
- Duration: ~12-18 hours on RTX 3080

### Master Summaries System

```
data/paper_processor/
├── master/
│   ├── summaries_master.jsonl          # Complete corpus (all papers)
│   ├── summaries_master_backup_<ts>.jsonl  # Auto-backup before append
│   └── master_index.json               # Dedupe key → line number lookup
├── monthly_deltas/
│   ├── delta_202510.jsonl              # October additions
│   ├── delta_202511.jsonl              # November additions
│   └── ...
├── summaries/
│   ├── summaries_20251006_123456.jsonl # Bootstrap run
│   └── summaries_20251106_234567.jsonl # Monthly run
└── latest.json
```

### Monthly Workflow

1. **Load dedupe keys** from master summaries
2. **Read new papers** from latest get_papers run
3. **Skip already-processed** papers (cross-run dedup)
4. **Process remaining** papers (~800-1,200 new)
5. **Append to master** (with auto-backup)
6. **Save monthly delta** (audit trail)
7. **Rebuild master index** (dedupe_key → line_num)
8. **Validate integrity** (line count vs index size)

### Cross-Run Deduplication

```python
# In monthly mode:
master_keys = load_dedupe_keys(master_summaries)  # e.g., {'pmid_12345', ...}
new_papers = load_papers(get_papers_output)

for paper in new_papers:
    if paper.dedupe_key in master_keys:
        skip()  # Already processed
    else:
        process_and_append()
```

## Configuration

### Command-Line Arguments

```bash
# Mode (required)
--mode MODE                 # 'bootstrap' or 'monthly'

# Monthly mode specific
--master-summaries PATH     # Required for monthly: master summaries file to append to
--resume-summaries PATH     # Disabled in monthly mode (use master instead)

# Common arguments
--papers-jsonl PATH         # Input JSONL (default: latest from get_papers)
--max-papers N              # Max papers to process (default: 200)
--batch-size N              # Keep at 1 to cap VRAM (default: 1)
--microbatch-size N         # Microbatch size (default: 1)
--ctx-tokens N              # Model context window (default: 16384)
--max-new-tokens N          # Max output tokens (default: 640)
--model NAME                # Model to use (default: mistralai/Mistral-7B-Instruct-v0.3)
--temperature T             # 0.0 for deterministic (default: 0.0)
--seed SEED                 # RNG seed for reproducibility

# Resumability & progress
--pointer-interval N        # Update latest.json every N input papers (default: 20)
--log-interval N            # Log progress every N successful outputs (default: 100)

# Fallback & input hygiene
--max-abstract-chars N      # Clamp abstract/content length before chunking (default: 20000)

# Performance/backoff
--slow-threshold-sec S      # Threshold for slow paper (default: 60)
--slow-backoff-sec S        # Sleep after slow paper (default: 1.0)
--exception-backoff-sec S   # Sleep after exceptions (default: 2.0)
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
├── master/                                         # Monthly mode outputs
│   ├── summaries_master.jsonl                     # Complete corpus (30K+ papers)
│   ├── summaries_master_backup_20251106_120000.jsonl  # Auto-backup
│   └── master_index.json                          # Fast lookup (dedupe_key → line)
├── monthly_deltas/                                # Monthly audit trail
│   ├── delta_202510.jsonl                         # October's new papers
│   ├── delta_202511.jsonl                         # November's new papers
│   └── ...
├── summaries/                                     # Individual run outputs
│   ├── summaries_20251006_123456.jsonl            # Bootstrap run
│   ├── summaries_20251106_234567.jsonl            # Monthly run
│   └── summaries_<timestamp>.jsonl.tmp            # In-progress (resume)
├── stats/                                         # Processing metrics
│   ├── stats_20251006_123456.json                 # Bootstrap stats
│   └── stats_20251106_234567.json                 # Monthly stats
└── latest.json                                    # Pointer to most recent run

logs/paper_processor/
└── paper_processor.log                            # Rotating file logger
```

### One-Time Setup for Monthly Updates

After bootstrap completes, initialize the master summaries:

```bash
# Copy bootstrap output to master directory
mkdir -p data/paper_processor/master
mkdir -p data/paper_processor/monthly_deltas

# Initialize master from bootstrap
cp data/paper_processor/summaries/summaries_<bootstrap_timestamp>.jsonl \
   data/paper_processor/master/summaries_master.jsonl

# Future monthly runs will append to this master file
```

## Telemetry & Stats

The processor tracks comprehensive metrics:

**Bootstrap Mode Stats:**
```json
{
  "run_id": "paper_processor_bootstrap_20251006_123456",
  "mode": "bootstrap",
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

**Monthly Mode Stats:**
```json
{
  "run_id": "paper_processor_monthly_20251106_234567",
  "mode": "monthly",
  "papers_in": 1200,
  "papers_out": 1150,
  "skipped_dedup": 850,                   // Already in master
  "papers_written_this_run": 350,         // Net additions
  
  "master_size_before": 28543,
  "master_size_after": 28893,
  "net_additions": 350,
  
  "monthly_delta_path": "data/paper_processor/monthly_deltas/delta_202511.jsonl",
  "master_index_valid": true,
  
  "elapsed_sec": 58320,
  "rate_papers_per_sec": 0.020,
  
  "model": "mistralai/Mistral-7B-Instruct-v0.3"
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

### Empty or Invalid Summaries

**Problem**: Model outputs invalid JSON

**Handled automatically**:
- Fulltext → abstract fallback on no chunks/validation errors/exceptions
- Two-pass extraction with targeted repair
- If neither fulltext nor abstract available: paper is skipped and counted

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
