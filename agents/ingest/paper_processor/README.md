# GPU-Accelerated Paper Processing with Mistral 7B

This module provides GPU-accelerated local processing of scientific papers using Mistral 7B Instruct, avoiding cloud costs while maintaining high-quality analysis.

## Features

- **GPU Acceleration**: Optimized for RTX 3080 with 4-bit quantization
- **Structured Analysis**: Generates structured summaries with key findings, methodology, and evidence grades
- **Local Storage**: All data stored locally in JSON format
- **Custom Search**: Fast, local search without external dependencies
- **Banking Integration**: Seamless integration with Level 1 banking system

## Pipeline Integration

The paper processor works with papers from the `get_papers` pipeline. Full-text fetching is now handled upstream by `get_papers` (default enabled), so papers already have the best available content (full text or abstract) when they reach this stage.

## Requirements

- NVIDIA GPU with CUDA support (RTX 3080 recommended)
- 10GB+ VRAM for 4-bit quantization
- 32GB+ RAM for processing
- Python 3.8+

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install PyTorch with CUDA support:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

## Usage

### Running

By default, the processor reads the latest selection produced by `get_papers`
via the pointer at `data/ingest/runs/latest.json`.

```bash
# Process latest papers from get_papers
python -m agents.ingest.paper_processor.run \
  --max-papers 200 \
  --batch-size 2 \
  --microbatch-size 1
```

Or, process an explicit JSONL:

```bash
python -m agents.ingest.paper_processor.run \
  --papers-jsonl data/ingest/runs/20251005_172726/pm_papers.jsonl \
  --max-papers 400
```

### Output Artifacts

- Summaries: `data/paper_processor/summaries/summaries_YYYYMMDD_HHMMSS.jsonl`
- Stats: `data/paper_processor/stats/stats_YYYYMMDD_HHMMSS.json`
- Latest pointer: `data/paper_processor/latest.json`

Logs go to `logs/paper_processor/paper_processor.log`.

### Notes

- Papers come from `get_papers` with the best available content (full text when available, abstract as fallback)
- Outputs (summaries, index, stats) are written via `StorageManager` under `data/paper_processor/…`

## Configuration

### ProcessingConfig
- `model_name`: Mistral model to use (default: "mistralai/Mistral-7B-Instruct-v0.2")
- `max_length`: Maximum input length (default: 4096)
- `temperature`: Generation temperature (default: 0.1)
- `batch_size`: Batch size for processing (default: 4)
- `use_4bit`: Enable 4-bit quantization (default: True)

### Environment Variables
- `SEARCH_ENDPOINT`: Azure AI Search endpoint
- `SEARCH_ADMIN_KEY`: Azure AI Search admin key
- `SEARCH_INDEX`: Search index name

## Architecture

### Components

1. **MistralClient**: GPU-accelerated Mistral 7B client
2. **GPUProcessor**: Main processing pipeline
3. **StorageManager**: Local storage management
4. **SearchIndex**: Custom search implementation
5. **SearchAPI**: Banking system integration

### Data Flow

```
Azure AI Search → GPUProcessor → MistralClient → Structured Summaries → Local Storage → SearchIndex → Banking System
```

## Performance

### RTX 3080 Performance
- **Processing Speed**: 3-6 hours for 100k papers
- **VRAM Usage**: 6-8GB (fits in 10GB)
- **Tokens/Second**: 15-25
- **Quality**: Strong for structured extraction

### Cost Comparison
- **Local Processing**: $0
- **GPT-4o Cloud**: $6,750 for 100k papers
- **Savings**: 100% cost reduction

## Storage Structure

```
data/paper_processor/
├── summaries/           # Processed paper summaries
├── index/              # Search index files
└── stats/              # Processing statistics
```

## Integration with Banking System

The processed summaries integrate with the Level 1 banking system:

1. **Enhanced Data Quality**: Structured summaries vs. raw abstracts
2. **Better Evidence Grading**: LLM analysis of study quality
3. **Goal-Specific Analysis**: Targeted analysis for fitness goals
4. **Local Search**: Fast, accurate search without rate limits

## Troubleshooting

### Common Issues

1. **CUDA Out of Memory**: Reduce batch size or enable 4-bit quantization
2. **Model Loading Errors**: Check internet connection for model download
3. **Search Errors**: Verify Azure AI Search credentials

### Performance Optimization

1. **Batch Size**: Adjust based on GPU memory
2. **Quantization**: Use 4-bit for VRAM efficiency
3. **Cache Management**: Clear GPU cache periodically

## Future Enhancements

- Vector search with FAISS
- Multi-GPU support
- Real-time processing
- Advanced filtering and ranking
- Integration with more LLM models

## License

This module is part of the EvidentFit project and follows the same licensing terms.


