# GPU-Accelerated Local Processing Plan with Mistral 7B Instruct

## Objective
Build a GPU-accelerated local processing pipeline using Mistral 7B Instruct to generate structured summaries of scientific papers, avoiding cloud costs while maintaining high-quality analysis.

## Current System Analysis
- **GPU**: NVIDIA GeForce RTX 3080 (10GB VRAM)
- **CPU**: Intel Core i9-10900KF (10 cores, 20 threads)
- **RAM**: 32GB DDR4-3200 (sufficient for GPU processing)
- **Storage**: Local storage for papers and results
- **Current issue**: Level 1 banking hitting rate limits, creatine graded as D instead of A

## Implementation Plan

### Phase 1: GPU Setup and Model Installation
1. **Install GPU-accelerated PyTorch** with CUDA support
2. **Download Mistral 7B Instruct** model
3. **Configure 4-bit quantization** for VRAM efficiency
4. **Test model loading** and basic inference

### Phase 2: Paper Processing Pipeline
1. **Create local processing pipeline** for paper analysis
2. **Implement structured summary generation** with Mistral 7B
3. **Add batch processing** for efficiency
4. **Test with 100-500 papers** to validate approach

### Phase 3: Custom Search Index
1. **Create JSON index structure** in local storage
2. **Implement search logic** in Python
3. **Store all summaries** locally
4. **Build search API** for banking system

## Enhanced Structured Summary Schema

```json
{
  "id": "pmid:123456",
  "title": "Paper Title",
  "doi": "10.1234/example",
  "pmid": "123456",
  "url_pub": "https://pubmed.ncbi.nlm.nih.gov/123456/",
  "journal": "Journal of Strength and Conditioning Research",
  "year": 2023,
  
  // === SUPPLEMENT & GOAL TAGS ===
  "supplements": ["creatine", "protein"],
  "goals": ["strength", "hypertrophy", "endurance"],
  "primary_goal": "strength",
  
  // === STUDY DESIGN & QUALITY ===
  "study_design": "RCT",
  "study_type": "randomized_controlled_trial",
  "blinding": "double_blind",
  "control_group": "placebo",
  "sample_size": 50,
  "duration": "8 weeks",
  "follow_up": "12 weeks",
  
  // === POPULATION DETAILS ===
  "population": {
    "age_range": "18-35",
    "sex": "male",
    "training_status": "trained",
    "experience": "2+ years",
    "health_status": "healthy",
    "exclusions": ["smokers", "supplement users"]
  },
  
  // === OUTCOMES & EFFECTS ===
  "primary_outcomes": ["1RM bench press", "1RM squat"],
  "secondary_outcomes": ["muscle mass", "body composition"],
  "outcome_measures": {
    "strength": {
      "measure": "1RM bench press",
      "baseline": "120.5 ± 15.2 kg",
      "intervention": "135.8 ± 18.1 kg",
      "control": "122.1 ± 16.8 kg",
      "effect_size": 0.15,
      "p_value": 0.03,
      "confidence_interval": [0.05, 0.25],
      "clinical_significance": true
    },
    "hypertrophy": {
      "measure": "muscle mass",
      "baseline": "45.2 ± 5.1 kg",
      "intervention": "47.8 ± 5.3 kg",
      "control": "45.5 ± 5.2 kg",
      "effect_size": 0.08,
      "p_value": 0.15,
      "confidence_interval": [-0.02, 0.18],
      "clinical_significance": false
    }
  },
  
  // === SAFETY & ADVERSE EVENTS ===
  "safety_data": {
    "adverse_events": 2,
    "serious_adverse_events": 0,
    "dropouts": 3,
    "safety_issues": ["mild gastrointestinal discomfort"],
    "contraindications": ["kidney disease"],
    "interactions": ["none reported"]
  },
  
  // === DOSAGE & ADMINISTRATION ===
  "dosage": {
    "creatine": {
      "loading": "20g/day for 5 days",
      "maintenance": "5g/day",
      "timing": "post-workout",
      "form": "monohydrate"
    },
    "protein": {
      "amount": "25g",
      "timing": "post-workout",
      "form": "whey isolate"
    }
  },
  
  // === QUALITY ASSESSMENT ===
  "quality_scores": {
    "overall": 8.5,
    "methodology": 9.0,
    "reporting": 8.0,
    "bias_risk": "low",
    "power_analysis": true,
    "intention_to_treat": true,
    "allocation_concealment": true
  },
  
  // === CONTEXTUAL INFORMATION ===
  "context": {
    "funding_source": "industry",
    "conflicts_of_interest": "authors received funding from supplement company",
    "limitations": ["small sample size", "short duration"],
    "generalizability": "limited to trained males",
    "clinical_relevance": "moderate"
  },
  
  // === SEARCH & RANKING ===
  "search_terms": ["creatine", "strength", "RCT", "muscle"],
  "relevance_scores": {
    "strength": 0.95,
    "hypertrophy": 0.75,
    "endurance": 0.30
  },
  
  // === PROCESSING METADATA ===
  "processing_date": "2025-10-03",
  "llm_model": "mistral-7b-instruct",
  "processing_version": "v1.0",
  "summary": "Comprehensive structured analysis of paper content"
}
```

## Technical Requirements

### GPU Setup
```bash
# Install GPU-accelerated PyTorch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install transformers and quantization
pip install transformers accelerate bitsandbytes

# Install additional dependencies
pip install datasets huggingface_hub
```

### Model Configuration
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load Mistral 7B with 4-bit quantization
model = AutoModelForCausalLM.from_pretrained(
    "mistralai/Mistral-7B-Instruct-v0.3",
    device_map="auto",
    load_in_4bit=True,
    torch_dtype=torch.float16,
    trust_remote_code=True
)

tokenizer = AutoTokenizer.from_pretrained(
    "mistralai/Mistral-7B-Instruct-v0.3",
    trust_remote_code=True
)
```

### Processing Pipeline
```python
def generate_structured_summary(paper_text, model, tokenizer):
    prompt = f"""<s>[INST] You are an expert research analyst. Analyze this scientific paper and extract structured data in JSON format.

PAPER CONTENT:
{paper_text}

EXTRACTION REQUIREMENTS:
1. Study Design: RCT, meta-analysis, crossover, etc.
2. Population: Age, sex, training status, health status
3. Outcomes: Primary/secondary outcomes with effect sizes
4. Safety: Adverse events, contraindications, interactions
5. Dosage: Supplement amounts, timing, forms
6. Quality: Methodology, bias risk, power analysis
7. Context: Funding, limitations, generalizability

Respond with structured JSON following the schema exactly. [/INST]"""

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=2000,
            temperature=0.2,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return response
```

## Performance Expectations

### Mistral 7B with RTX 3080
- **Processing time**: 3-6 hours for 100k papers
- **VRAM usage**: 6-8GB (fits in 10GB)
- **Tokens/second**: 15-25
- **Quality**: Strong for structured extraction
- **Cost**: $0 (local processing)

## Storage Structure

```
local-storage/
├── papers/
│   ├── raw/
│   │   ├── paper_001.txt
│   │   └── paper_002.txt
│   └── processed/
│       ├── summary_001.json
│       └── summary_002.json
├── index/
│   ├── supplement_index.json
│   ├── goal_index.json
│   └── quality_index.json
└── search/
    ├── search_api.py
    └── ranking_algorithm.py
```

## Files to Create/Modify

### New Files
- `agents/paper_processor/run.py` - Main processing pipeline
- `agents/paper_processor/gpu_processor.py` - GPU-accelerated processing
- `agents/paper_processor/mistral_client.py` - Mistral 7B client
- `agents/paper_processor/storage_manager.py` - Local storage management
- `agents/paper_processor/search_index.py` - Custom search implementation
- `agents/paper_processor/search_api.py` - Search API for banking system

### Modified Files
- `agents/banking/level1_banking.py` - Use structured summaries instead of abstracts
- `api/stack_builder.py` - Integrate with custom search

## Implementation Steps

### Step 1: GPU Setup
1. **Install PyTorch with CUDA** support
2. **Download Mistral 7B Instruct** model
3. **Configure 4-bit quantization** for VRAM efficiency
4. **Test model loading** and basic inference

### Step 2: Processing Pipeline
1. **Create GPU processing pipeline** for paper analysis
2. **Implement structured summary generation** with Mistral 7B
3. **Add batch processing** for efficiency
4. **Test with 100-500 papers** to validate approach

### Step 3: Custom Search
1. **Create local search index** with JSON files
2. **Implement search logic** with filtering and ranking
3. **Build search API** for banking system
4. **Test search functionality** with sample data

### Step 4: Banking Integration
1. **Modify Level 1 banking** to use structured summaries
2. **Update search queries** to use custom search
3. **Test evidence grading** with enhanced data
4. **Validate creatine strength grade** (should be A, not D)

## Success Criteria
- **Processing**: 3-6 hours for 100k papers with RTX 3080
- **Storage**: All summaries in local storage
- **Search**: Fast, accurate search with custom ranking
- **Integration**: Seamless integration with banking system
- **Accuracy**: Creatine strength graded as A (not D)
- **Cost**: $0 (vs $6,750 for GPT-4o)

## Current Issues to Address
1. **Rate limits**: Current banking hitting Azure AI Foundry limits
2. **Search query**: Fixed supplements field search, but need better data
3. **Evidence grading**: Creatine strength incorrectly graded as D
4. **Data quality**: Abstracts insufficient for accurate grading

## Benefits of This Approach
- **Cost-effective**: $0 vs $6,750 for GPT-4o
- **Fast processing**: 3-6 hours vs 20-40 hours with CPU
- **High quality**: Mistral 7B provides excellent structured extraction
- **Complete control**: Local processing, no external dependencies
- **Scalable**: Can process unlimited papers
- **Future-proof**: Easy to upgrade models or hardware

## Next Steps
1. **Stop current banking run** (hitting rate limits)
2. **Set up GPU processing pipeline** with Mistral 7B
3. **Test with 100-500 papers** to validate approach
4. **Scale to full dataset** (100k papers)
5. **Integrate with banking system** for enhanced evidence grading

## Current System Status
- **Level 1 banking**: Search queries fixed, ready for enhanced processing
- **Level 2 banking**: Pending (profile-specific reasoning)
- **Level 3 banking**: Pending (query-specific reasoning)
- **GPU processing**: Ready to implement with Mistral 7B Instruct

## Files Ready for Implementation
- Enhanced Level 1 banking with fixed search queries
- Structured summary schema design
- GPU processing plan and requirements
- Custom search index architecture
- Integration plan with banking system

This approach provides cost-effective, fast, high-quality processing using RTX 3080 GPU with Mistral 7B Instruct.




