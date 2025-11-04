# Agent B: Paper Processor

## Overview

The Paper Processor extracts structured data from research papers using LLM analysis. It processes papers from the ingestion pipeline and creates "evidence cards" with population, intervention, outcomes, and safety information.

## LLM Model

**Model**: GPT-4o-mini (Azure AI Foundry) - **Default and Recommended**
- **Cost**: ~$24.30 per 30K papers (initial), ~$0.81-1.62 per 1-2K papers (monthly)
- **Runtime**: 2-3 hours for 30K papers, 10-20 minutes for 1-2K papers (parallel execution)
- **Quality**: Better JSON compliance and extraction accuracy than local models
- **See**: `docs/MODEL_SELECTION.md` and `docs/PAPER_PROCESSOR_MODEL_COMPARISON.md` for detailed rationale

**Legacy Option**: Mistral-7B local GPU available via `PAPER_PROCESSOR_USE_CLOUD=0`, but not recommended.

## Usage

### Basic Usage

```bash
# Process papers with GPT-4o-mini (default)
python -m agents.paper_processor.run --max-papers 2000

# Process all papers
python -m agents.paper_processor.run
```

### Configuration

Set environment variables:
- `FOUNDATION_ENDPOINT` - Azure AI Foundry endpoint
- `FOUNDATION_KEY` - Azure AI Foundry API key
- `FOUNDATION_CHAT_MODEL` - Model name (default: gpt-4o-mini)
- `PAPER_PROCESSOR_USE_CLOUD` - Set to "0" to use legacy Mistral-7B local GPU

### Legacy Local GPU Mode

To use Mistral-7B local GPU instead of GPT-4o-mini:

```bash
export PAPER_PROCESSOR_USE_CLOUD=0
python -m agents.paper_processor.run --max-papers 2000 --quant 4bit
```

## Output

The processor creates evidence cards with:
- **Population**: Sample size, demographics, training status
- **Intervention**: Dosing, duration, supplement forms, loading phases
- **Outcomes**: Effect sizes, statistical significance, measures
- **Safety**: Adverse events, contraindications, safety grades

Cards are stored in:
- Database: `data/cards/` (via database writer)
- JSONL files: `data/paper_processor/summaries/`

## Performance

- **30K papers**: ~$24.30, 2-3 hours
- **1-2K papers**: ~$0.81-1.62, 10-20 minutes
- **Quality**: 92-95% extraction accuracy (better than local models)

## See Also

- `docs/MODEL_SELECTION.md` - Model selection rationale
- `docs/PAPER_PROCESSOR_MODEL_COMPARISON.md` - Detailed comparison with Mistral-7B
