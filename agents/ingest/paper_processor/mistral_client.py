"""
GPU-accelerated Mistral 7B Instruct client for paper processing.
Optimized for RTX 3080 with 4-bit quantization.
"""

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, StoppingCriteria, StoppingCriteriaList
from typing import Dict, List, Optional, Any, Tuple
import logging
import time
from dataclasses import dataclass
import re
import json
import unicodedata
try:
    from jsonschema import validate as jsonschema_validate
    from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
except Exception:  # jsonschema optional
    jsonschema_validate = None
    JSONSchemaValidationError = Exception

logger = logging.getLogger(__name__)
torch.set_float32_matmul_precision("high")

class StopOnSentinel(StoppingCriteria):
    """Stop when a unique sentinel appears at the end of the stream."""
    def __init__(self, tokenizer, sentinel="### END_JSON"):
        self.ids = tokenizer.encode(sentinel, add_special_tokens=False)
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        n = len(self.ids)
        if input_ids.shape[1] < n:
            return False
        return input_ids[0, -n:].tolist() == self.ids

@dataclass
class ProcessingConfig:
    """Configuration for Mistral 7B processing."""
    model_name: str = "mistralai/Mistral-7B-Instruct-v0.3"
    ctx_tokens: int = 16384          # effective context window for 3080 10GB
    max_new_tokens: int = 640        # still generous, slightly faster than 768
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    repetition_penalty: float = 1.1
    batch_size: int = 8              # papers per outer batch
    microbatch_size: int = 4         # prompts per generate() call (used below)
    json_stop: str = "### END_JSON"
    use_4bit: bool = True
    device_map: str = "auto"
    # Validation / repair
    enable_schema_validation: bool = True
    enable_model_repair: bool = False
    schema_version: str = "v1.1"

class MistralClient:
    """GPU-accelerated Mistral 7B client for structured paper analysis."""
    
    def __init__(self, config: ProcessingConfig = None):
        self.config = config or ProcessingConfig()
        self.tokenizer = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._setup_model()
    
    def _setup_model(self):
        """Initialize Mistral 7B with 4-bit quantization for RTX 3080."""
        try:
            logger.info(f"Setting up Mistral 7B on {self.device}")
            
            # Configure 4-bit quantization for VRAM efficiency
            if self.config.use_4bit and self.device == "cuda":
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
            else:
                quantization_config = None
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name,
                trust_remote_code=True
            )
            
            # Configure tokenizer for batched generation
            self.tokenizer.padding_side = "left"   # safer for batched causal generation
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model with quantization
            # Try flash attention 2 first, fall back to default if not available
            try:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_name,
                    quantization_config=quantization_config,
                    device_map=self.config.device_map,
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    attn_implementation="flash_attention_2"
                )
            except (ImportError, ValueError) as e:
                # Fall back to default attention if flash_attn not available or memory issues
                logger.warning(f"Flash attention failed: {e}, falling back to default attention")
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_name,
                    quantization_config=quantization_config,
                    device_map=self.config.device_map,
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            try:
                # Enable flash-sdp kernels if available (speeds up attention on Ampere)
                if torch.backends.cuda.sdp_kernel is not None:
                    torch.backends.cuda.enable_flash_sdp(True)
                    torch.backends.cuda.enable_math_sdp(True)
                    torch.backends.cuda.enable_mem_efficient_sdp(True)
            except Exception:
                pass
            
            logger.info("Mistral 7B model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup Mistral model: {e}")
            raise
    
    def _fit_inputs(self, prompts: List[str]) -> Dict[str, torch.Tensor]:
        """Fit inputs to context window, enforcing input_len <= ctx_tokens - max_new_tokens."""
        allow_in = self.config.ctx_tokens - self.config.max_new_tokens
        enc = self.tokenizer(
            prompts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=allow_in
        )
        # Debug: token lengths
        lengths = enc["attention_mask"].sum(dim=1).tolist()
        logger.info(f"Token lengths (first 8): {lengths[:8]} | allow_in={allow_in}")
        return enc

    def _iter_microbatches(self, seqs: List[str], mb: int):
        for i in range(0, len(seqs), mb):
            yield seqs[i:i+mb], i

    def _adaptive_mb(self, input_lengths: List[int]) -> int:
        """
        Pick a microbatch size based on token lengths to keep KV cache small.
        Heuristic for 10GB VRAM (RTX 3080):
          target <= ~4,500 prompt tokens per microbatch.
        We'll cap at self.config.microbatch_size and never go below 1.
        """
        if not input_lengths:
            return max(1, self.config.microbatch_size)
        max_len = max(input_lengths)  # worst prompt in this run
        # 4500 // max_len (at least 1), but don't exceed configured microbatch_size
        est = max(1, min(self.config.microbatch_size, 4500 // max(1, max_len)))
        return est
    
    def generate_batch_summaries(self, papers_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate structured summaries for a batch of papers.
        
        Args:
            papers_data: List of paper data with title, abstract, etc.
            
        Returns:
            List of structured summaries with key findings, methodology, etc.
        """
        try:
            # Create prompts for batch processing
            prompts = []
            for paper_data in papers_data:
                prompt = self._create_analysis_prompt(paper_data)
                prompts.append(prompt)
            
            # Micro-batch through prompts to keep KV cache small and stabilize decoding
            device = next(self.model.parameters()).device
            stop_criteria = StoppingCriteriaList([StopOnSentinel(self.tokenizer, self.config.json_stop)])
            summaries = []

            # Pre-tokenize once to compute prompt lengths and choose adaptive microbatch size
            probe = self._fit_inputs(prompts)
            lengths = probe["attention_mask"].sum(dim=1).tolist()
            mb = self._adaptive_mb(lengths)
            logger.info(f"Adaptive microbatch_size={mb} (requested {self.config.microbatch_size}, max_len={max(lengths) if lengths else 0})")

            for start in range(0, len(prompts), mb):
                sub = prompts[start:start + mb]
                inputs = self._fit_inputs(sub)
                input_ids = inputs["input_ids"].to(device)
                attention_mask = inputs["attention_mask"].to(device)

                with torch.no_grad():
                    outputs = self.model.generate(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        max_new_tokens=self.config.max_new_tokens,
                        do_sample=(self.config.temperature > 0.2),  # unchanged behavior
                        temperature=self.config.temperature,
                        top_p=self.config.top_p,
                        top_k=self.config.top_k,
                        repetition_penalty=self.config.repetition_penalty,
                        use_cache=True,
                        pad_token_id=self.tokenizer.eos_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                        stopping_criteria=stop_criteria,
                        early_stopping=False
                    )

                for row, output in enumerate(outputs):
                    src_len = input_ids[row].shape[0]
                    new_tokens = output[src_len:]
                    response = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
                    response = self._safe_text(response)
                    response = self._strip_code_fences(response)
                    response = self._trim_and_balance_json(response, self.config.json_stop)
                    try:
                        idx = start + row
                        summary = self._parse_structured_summary(response, papers_data[idx])
                    except Exception as e:
                        logger.error(f"Parse error: {e}")
                        summary = self._create_fallback_summary(papers_data[idx])
                    summaries.append(summary)
                if self.device == "cuda":
                    torch.cuda.empty_cache()
            
            return summaries
            
        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            # Return fallback summaries
            return [self._create_fallback_summary(paper_data) for paper_data in papers_data]

    def generate_many(
        self,
        prompts: List[str],
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        do_sample: bool = False
    ) -> List[str]:
        """
        Lightweight batch generator for benchmarking.
        Returns RAW TEXT (no JSON parsing), one string per prompt.
        """
        device = next(self.model.parameters()).device
        stop_criteria = StoppingCriteriaList([StopOnSentinel(self.tokenizer, self.config.json_stop)])

        # microbatch through prompts to keep KV cache small
        outs: List[str] = []
        prompts = list(prompts)
        for start in range(0, len(prompts), self.config.microbatch_size):
            sub = prompts[start:start + self.config.microbatch_size]
            enc = self._fit_inputs(sub)
            input_ids = enc["input_ids"].to(device)
            attention_mask = enc["attention_mask"].to(device)

            with torch.no_grad():
                gen = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_new_tokens,
                    do_sample=do_sample and (temperature > 0.0),
                    temperature=temperature,
                    top_p=self.config.top_p,
                    top_k=self.config.top_k,
                    repetition_penalty=self.config.repetition_penalty,
                    use_cache=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    stopping_criteria=stop_criteria,
                    early_stopping=False
                )

            for row, output in enumerate(gen):
                src_len = input_ids[row].shape[0]
                new_tokens = output[src_len:]
                text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
                # keep it raw but remove code fences and clamp at sentinel/last brace
                text = self._safe_text(text)
                text = self._strip_code_fences(text)
                text = self._trim_and_balance_json(text, self.config.json_stop)
                outs.append(text)

            if self.device == "cuda":
                torch.cuda.empty_cache()

        return outs

    def generate_single(self, prompt: str) -> str:
        """Generate a single response from a prompt."""
        device = next(self.model.parameters()).device
        stop_criteria = StoppingCriteriaList([StopOnSentinel(self.tokenizer, self.config.json_stop)])
        
        # Tokenize and fit to context
        inputs = self._fit_inputs([prompt])
        input_ids = inputs["input_ids"].to(device)
        attention_mask = inputs["attention_mask"].to(device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.config.max_new_tokens,
                do_sample=(self.config.temperature > 0.2),
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                top_k=self.config.top_k,
                repetition_penalty=self.config.repetition_penalty,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                stopping_criteria=stop_criteria,
                early_stopping=False
            )
        
        # Decode response
        src_len = input_ids.shape[1]
        new_tokens = outputs[0][src_len:]
        response = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        response = self._safe_text(response)
        response = self._strip_code_fences(response)
        response = self._trim_and_balance_json(response, self.config.json_stop)
        
        return response

    def generate_structured_summary(self, paper_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate structured summary for a single paper.
        
        Args:
            paper_data: Paper data with title, abstract, etc.
            
        Returns:
            Structured summary with key findings, methodology, etc.
        """
        try:
            # Use batch processing for single paper
            summaries = self.generate_batch_summaries([paper_data])
            return summaries[0] if summaries else self._create_fallback_summary(paper_data)
            
        except Exception as e:
            logger.error(f"Error in single paper processing: {e}")
            return self._create_fallback_summary(paper_data)
    
    def _create_analysis_prompt(self, paper_data: Dict[str, Any]) -> str:
        """Create comprehensive structured analysis prompt for the paper."""
        title = paper_data.get('title', 'Unknown Title')
        abstract = paper_data.get('summary', paper_data.get('content', ''))
        journal = paper_data.get('journal', 'Unknown Journal')
        year = paper_data.get('year', 'Unknown Year')
        study_type = paper_data.get('study_type', 'Unknown Type')
        known_meta = self._preextract_metadata(paper_data, abstract)
        
        prompt = f"""<s>[INST] You are an expert research analyst. Analyze this scientific paper and extract comprehensive structured data in JSON.

Rules:
- Return ONLY valid JSON that matches the schema.
- If a field is not present in the provided text, return null or [] (do NOT guess).
- Use numbers for numeric fields; preserve units in strings exactly as written.
- If there are multiple measures for the same outcome domain (e.g., two strength tests), return them as an ARRAY under that domain (do NOT repeat the key).
- Include for each numeric claim an "evidence_text" (the exact sentence/phrase from the paper) when possible.
- For p-values and confidence intervals, include both machine-usable numbers and raw text. Example:
  "p_value_num": 0.001, "p_value_text": "<0.001"; "confidence_interval": [0.05, 0.25], "ci_text": "95% CI [0.05, 0.25]".
- Do not include markdown code fences or ```json tags.
- Output must start with "{{" and, after the final closing brace, include a newline followed by the exact text: ### END_JSON

PAPER DETAILS:
Title: {title}
Journal: {journal}
Year: {year}
Study Type: {study_type}

KNOWN_METADATA (authoritative; use these values unless contradicted by context):
{json.dumps(known_meta, ensure_ascii=False)}

ABSTRACT:
{abstract}

Return JSON with ALL these fields (fill missing with null/[]), then stop:
{{
    "id": "Paper identifier",
    "title": "Paper title",
    "journal": "Journal name",
    "year": "Publication year",
    "study_type": "Study type",
    "supplements": ["List of supplements"],
    "goals": ["List of fitness goals"],
    "primary_goal": "Primary goal",
    "study_design": "Study design",
    "population": {{
        "age_range": "Age range",
        "sex": "Sex",
        "training_status": "Training status",
        "experience": "Experience level",
        "health_status": "Health status",
        "exclusions": ["Exclusion criteria"]
    }},
    "outcome_measures": {{
        "strength": [
            {{"measure": "Outcome name", "effect_size": 0.0, "p_value_num": null, "p_value_text": null}}
        ],
        "endurance": [
            {{"measure": "Outcome name", "effect_size": 0.0, "p_value_num": null, "p_value_text": null}}
        ],
        "power": []
    }},
    "safety_data": {{
        "adverse_events": "Number of adverse events (numeric if available)",
        "serious_adverse_events": "Number of serious events",
        "dropouts": "Number of dropouts",
        "safety_issues": ["Safety issues"],
        "contraindications": ["Contraindications"],
        "interactions": ["Drug interactions"]
    }},
    "dosage": {{
        "supplement_name": {{
            "loading": "Loading dose",
            "maintenance": "Maintenance dose",
            "timing": "Timing",
            "form": "Form"
        }}
    }},
    "quality_scores": {{
        "overall": 8.0,
        "methodology": 8.0,
        "reporting": 8.0,
        "bias_risk": "low",
        "power_analysis": true,
        "intention_to_treat": true,
        "allocation_concealment": true
    }},
    "context": {{
        "funding_source": "Funding source",
        "conflicts_of_interest": "Conflicts",
        "limitations": ["Limitations"],
        "generalizability": "Generalizability",
        "clinical_relevance": "Clinical relevance"
    }},
    "search_terms": ["Search terms"],
    "relevance_scores": {{
        "strength": 0.8,
        "hypertrophy": 0.6,
        "endurance": 0.4
    }},
    "summary": "Brief summary",
    "key_findings": ["Key findings"],
    "evidence_grade": "A",
    "schema_version": "{self.config.schema_version}"
}}

After the closing brace, output a newline and the exact text:
### END_JSON
[/INST]
"""
        
        return prompt
    
    def _parse_structured_summary(self, response: str, paper_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the structured response from Mistral."""
        # Debug: Print the raw response
        print(f"DEBUG: Raw model response (first 200 chars): {response[:200]}")
        print(f"DEBUG: Raw model response length: {len(response)}")
        print(f"DEBUG: Full raw response: {response}")
        
        try:
            import json
            import re
            
            # Clean response (already trimmed/balanced upstream, but keep safe)
            response = response.strip()
            
            # Prefer the longest balanced top-level JSON object
            response = self._longest_balanced_slice(response)
            
            # Try to parse JSON directly first
            try:
                structured_data = json.loads(response)
            except json.JSONDecodeError:
                # If direct parsing fails, try to fix common issues
                response = self._fix_json_issues(response)
                try:
                    structured_data = json.loads(response)
                except json.JSONDecodeError:
                    # If still failing, try a more aggressive fix
                    response = self._aggressive_json_fix(response)
                    try:
                        structured_data = json.loads(response)
                    except json.JSONDecodeError:
                        # Final fallback - try to extract key-value pairs manually
                        structured_data = self._manual_json_extraction(response)

            # Post-processing: coerce stats fields, attach evidence spans, normalize outcomes if present
            try:
                if hasattr(self, "_normalize_outcomes"):
                    self._normalize_outcomes(structured_data)
                self._coerce_stats_fields(structured_data)
                self._attach_evidence_spans(structured_data, paper_data.get('content') or paper_data.get('summary') or "")
                if hasattr(self, "_validate_outcomes"):
                    self._validate_outcomes(structured_data)
            except Exception as _:
                pass

            # Fill defaults BEFORE schema validation to avoid trivial fails
            self._fill_required_defaults(structured_data)

            # Schema validation (optional)
            if self.config.enable_schema_validation and jsonschema_validate is not None:
                ok, err = self._validate_against_schema(structured_data)
                if not ok and self.config.enable_model_repair:
                    try:
                        repair_prompt = self._build_repair_prompt(structured_data, err)
                        fixed = self._repair_with_model(repair_prompt)
                        if fixed:
                            structured_data = fixed
                    except Exception as _:
                        pass
            
            # Add metadata
            structured_data['paper_id'] = paper_data.get('id', 'unknown')
            structured_data['paper_title'] = paper_data.get('title', 'Unknown')
            structured_data['paper_journal'] = paper_data.get('journal', 'Unknown')
            structured_data['paper_year'] = paper_data.get('year', 'Unknown')
            structured_data['paper_study_type'] = paper_data.get('study_type', 'Unknown')
            structured_data['processing_timestamp'] = time.time()
            structured_data['llm_model'] = self.config.model_name
            structured_data['schema_version'] = self.config.schema_version
            
            return structured_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.warning(f"Response was: {response[:200]}...")
            return self._create_fallback_summary(paper_data)
        except Exception as e:
            logger.error(f"Error parsing structured response: {e}")
            logger.error(f"Response was: {response[:200]}...")
            return self._create_fallback_summary(paper_data)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information for logging."""
        return {
            'model_name': self.config.model_name,
            'device': self.device,
            'batch_size': self.config.batch_size,
            'use_4bit': self.config.use_4bit,
            'max_length': self.config.max_length,
            'max_new_tokens': self.config.max_new_tokens
        }
    
    def cleanup(self):
        """Clean up model and free memory."""
        if self.model:
            del self.model
        if self.tokenizer:
            del self.tokenizer
        torch.cuda.empty_cache()
    
    def _fix_json_issues(self, json_str: str) -> str:
        """Fix common JSON formatting issues with robust handling."""
        import re
        
        # Remove invalid control characters first
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        
        # Remove trailing commas more aggressively
        # Handle trailing commas before closing braces and brackets
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix unquoted keys (but be careful not to break string values)
        json_str = re.sub(r'(\w+):', r'"\1":', json_str)
        
        # Fix single quotes to double quotes
        json_str = json_str.replace("'", '"')
        
        # Fix unescaped quotes in string values - handle the specific pattern we're seeing
        # Pattern: "title": "Text with "quoted" word"
        # We need to escape the inner quotes
        json_str = re.sub(r'("title":\s*"[^"]*)"([^"]*)"([^"]*")', r'\1\\"\2\\"\3', json_str)
        
        # Fix double quotes that were created by the regex
        json_str = json_str.replace('""', '"')
        
        # Remove any non-JSON text before/after
        json_str = json_str.strip()
        
        # Ensure proper JSON structure
        if not json_str.startswith('{'):
            json_str = '{' + json_str
        if not json_str.endswith('}'):
            json_str = json_str + '}'
        
        # Final cleanup - remove any remaining trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        return json_str
    
    def _aggressive_json_fix(self, json_str: str) -> str:
        """More aggressive JSON fixing for severely malformed JSON."""
        import re
        
        # Remove all control characters
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        
        # Remove trailing commas everywhere
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix unquoted keys
        json_str = re.sub(r'(\w+):', r'"\1":', json_str)
        
        # Fix single quotes
        json_str = json_str.replace("'", '"')
        
        # Remove any text before the first { and after the last }
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx + 1]
        
        # Ensure we have a valid JSON structure
        if not json_str.startswith('{'):
            json_str = '{' + json_str
        if not json_str.endswith('}'):
            json_str = json_str + '}'
        
        # Final trailing comma cleanup
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        return json_str
    
    def _manual_json_extraction(self, json_str: str) -> Dict[str, Any]:
        """Manually extract key-value pairs from malformed JSON using full schema."""
        import re
        
        result = {}
        
        # Extract basic fields
        title_match = re.search(r'"title":\s*"([^"]*(?:\\.[^"]*)*)"', json_str)
        if title_match:
            result['title'] = title_match.group(1).replace('\\"', '"')
        
        # Extract supplements
        supplements_match = re.search(r'"supplements":\s*\[(.*?)\]', json_str)
        if supplements_match:
            supplements_str = supplements_match.group(1)
            supplements = re.findall(r'"([^"]*)"', supplements_str)
            result['supplements'] = supplements
        
        # Extract goals
        goals_match = re.search(r'"goals":\s*\[(.*?)\]', json_str)
        if goals_match:
            goals_str = goals_match.group(1)
            goals = re.findall(r'"([^"]*)"', goals_str)
            result['goals'] = goals
        
        # Extract study_type
        study_type_match = re.search(r'"study_type":\s*"([^"]*)"', json_str)
        if study_type_match:
            result['study_type'] = study_type_match.group(1)
        
        # Extract population (handle nested structure)
        population_match = re.search(r'"population":\s*\{([^}]*)\}', json_str)
        if population_match:
            population_str = population_match.group(1)
            population = {}
            age_match = re.search(r'"age_range":\s*"([^"]*)"', population_str)
            if age_match:
                population['age_range'] = age_match.group(1)
            sex_match = re.search(r'"sex":\s*"([^"]*)"', population_str)
            if sex_match:
                population['sex'] = sex_match.group(1)
            result['population'] = population
        
        # Extract primary_outcomes
        primary_outcomes_match = re.search(r'"primary_outcomes":\s*\[(.*?)\]', json_str)
        if primary_outcomes_match:
            outcomes_str = primary_outcomes_match.group(1)
            outcomes = re.findall(r'"([^"]*)"', outcomes_str)
            result['primary_outcomes'] = outcomes
        
        # Extract secondary_outcomes
        secondary_outcomes_match = re.search(r'"secondary_outcomes":\s*\[(.*?)\]', json_str)
        if secondary_outcomes_match:
            outcomes_str = secondary_outcomes_match.group(1)
            outcomes = re.findall(r'"([^"]*)"', outcomes_str)
            result['secondary_outcomes'] = outcomes
        
        # Extract quality_scores (handle nested structure)
        quality_match = re.search(r'"quality_scores":\s*\{([^}]*)\}', json_str)
        if quality_match:
            quality_str = quality_match.group(1)
            quality_scores = {}
            overall_match = re.search(r'"overall":\s*([0-9.]+)', quality_str)
            if overall_match:
                quality_scores['overall'] = float(overall_match.group(1))
            result['quality_scores'] = quality_scores
        
        # Extract safety_data (handle nested structure)
        safety_match = re.search(r'"safety_data":\s*\{([^}]*)\}', json_str)
        if safety_match:
            safety_str = safety_match.group(1)
            safety_data = {}
            adverse_match = re.search(r'"adverse_events":\s*"([^"]*)"', safety_str)
            if adverse_match:
                safety_data['adverse_events'] = adverse_match.group(1)
            result['safety_data'] = safety_data
        
        # Extract summary
        summary_match = re.search(r'"summary":\s*"([^"]*)"', json_str)
        if summary_match:
            result['summary'] = summary_match.group(1)
        
        # Ensure we have at least the basic fields with proper structure
        if 'title' not in result:
            result['title'] = 'Unknown Title'
        if 'supplements' not in result:
            result['supplements'] = ['unknown']
        if 'goals' not in result:
            result['goals'] = ['general']
        if 'study_type' not in result:
            result['study_type'] = 'Unknown'
        if 'population' not in result:
            result['population'] = {
                'age_range': 'unknown',
                'sex': 'unknown',
                'training_status': 'unknown',
                'experience': 'unknown',
                'health_status': 'unknown',
                'exclusions': []
            }
        if 'primary_outcomes' not in result:
            result['primary_outcomes'] = []
        if 'secondary_outcomes' not in result:
            result['secondary_outcomes'] = []
        if 'quality_scores' not in result:
            result['quality_scores'] = {
                'overall': 5.0,
                'methodology': 5.0,
                'reporting': 5.0,
                'bias_risk': 'unknown',
                'power_analysis': False,
                'intention_to_treat': False,
                'allocation_concealment': False
            }
        if 'safety_data' not in result:
            result['safety_data'] = {
                'adverse_events': 'unknown',
                'serious_adverse_events': 'unknown',
                'dropouts': 'unknown',
                'safety_issues': [],
                'contraindications': [],
                'interactions': []
            }
        
        return result

    # -------- JSON trimming & balance utilities --------
    def _strip_code_fences(self, s: str) -> str:
        t = s.lstrip()
        if t.startswith("```json"):
            t = t[7:]
        if t.startswith("```"):
            t = t[3:]
        if t.endswith("```"):
            t = t[:-3]
        return t

    def _trim_and_balance_json(self, resp: str, sentinel: str) -> str:
        # Trim at sentinel if present
        if sentinel and sentinel in resp:
            resp = resp.split(sentinel, 1)[0]
        # Clamp at last closing brace
        last = resp.rfind("}")
        if last != -1:
            resp = resp[:last+1]
        # Balance braces (append up to 8)
        open_b, close_b = resp.count("{"), resp.count("}")
        deficit = open_b - close_b
        if 0 < deficit <= 8:
            resp += "}" * deficit
        return resp.strip()

    def _longest_balanced_slice(self, s: str) -> str:
        """Return the longest prefix that forms a balanced top-level JSON object."""
        start = s.find("{")
        if start == -1:
            raise ValueError("No JSON object found in response")
        depth = 0
        end = -1
        for i, ch in enumerate(s[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
        if end != -1:
            return s[start:end]
        # As a fallback, append braces up to 8 to close
        deficit = s[start:].count("{") - s[start:].count("}")
        deficit = min(max(deficit, 0), 8)
        return (s[start:] + ("}" * deficit)).strip()
    
    def _create_fallback_summary(self, paper_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a fallback summary when parsing fails."""
        return {
            'paper_id': paper_data.get('id', 'unknown'),
            'paper_title': paper_data.get('title', 'Unknown'),
            'paper_journal': paper_data.get('journal', 'Unknown'),
            'paper_year': paper_data.get('year', 'Unknown'),
            'paper_study_type': paper_data.get('study_type', 'Unknown'),
            'key_findings': 'Analysis failed - using fallback summary',
            'methodology': 'Unable to extract methodology',
            'population': 'Unable to extract population details',
            'intervention': 'Unable to extract intervention details',
            'outcomes': 'Unable to extract outcomes',
            'effect_size': 'Unable to extract effect size',
            'limitations': 'Unable to extract limitations',
            'clinical_significance': 'Unable to extract clinical significance',
            'evidence_quality': 'C',  # Default to C grade
            'supplement_relevance': 'Unable to assess relevance',
            'processing_timestamp': time.time(),
            'fallback': True
        }
    
    def process_batch(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a batch of papers efficiently."""
        results = []
        
        for i in range(0, len(papers), self.config.batch_size):
            batch = papers[i:i + self.config.batch_size]
            logger.info(f"Processing batch {i//self.config.batch_size + 1}/{(len(papers)-1)//self.config.batch_size + 1}")
            
            for paper in batch:
                try:
                    summary = self.generate_structured_summary(paper)
                    results.append(summary)
                except Exception as e:
                    logger.error(f"Error processing paper {paper.get('id', 'unknown')}: {e}")
                    results.append(self._create_fallback_summary(paper))
            
            # Clear GPU cache periodically
            if self.device == "cuda":
                torch.cuda.empty_cache()
        
        return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        return {
            'model_name': self.config.model_name,
            'device': self.device,
            'use_4bit': self.config.use_4bit,
            'ctx_tokens': self.config.ctx_tokens,
            'batch_size': self.config.batch_size,
            'cuda_available': torch.cuda.is_available(),
            'cuda_device_count': torch.cuda.device_count() if torch.cuda.is_available() else 0,
            'cuda_device_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        }

    def _normalize_outcomes(self, data: Dict[str, Any]) -> None:
        """
        Coerce outcome_measures into a dict of arrays so multiple measures per domain are preserved.
        Accepts three shapes:
          A) {"strength": {...}, "endurance": {...}}  -> wrap dicts as single-item lists.
          B) {"strength": [ {...}, {...} ], ... }     -> keep as-is.
          C) [ {"domain":"strength", ...}, ... ]      -> group into dict-of-arrays.
        """
        om = data.get("outcome_measures")
        if om is None:
            return
        # Case C: flat list with "domain"
        if isinstance(om, list):
            grouped = {}
            for item in om:
                if isinstance(item, dict):
                    dom = str(item.get("domain", "unknown")).lower()
                    grouped.setdefault(dom, []).append(item)
            data["outcome_measures"] = grouped
            return
        # Case A/B: dict -> ensure values are lists
        if isinstance(om, dict):
            for k, v in list(om.items()):
                if v is None:
                    om[k] = []
                elif isinstance(v, dict):
                    om[k] = [v]
                elif isinstance(v, list):
                    # ensure list of dicts (leave cleaning to validator)
                    pass
                else:
                    om[k] = [v]

    def _validate_outcomes(self, data: Dict[str, Any]) -> None:
        """
        Light cleanup: ensure each domain is a list of dicts with a 'measure' key; drop malformed items.
        """
        om = data.get("outcome_measures")
        if not isinstance(om, dict):
            return
        for dom, lst in list(om.items()):
            if not isinstance(lst, list):
                om[dom] = []
                continue
            cleaned = []
            for x in lst:
                if isinstance(x, dict) and x.get("measure"):
                    cleaned.append(x)
            om[dom] = cleaned

    # ---------------------------
    # Helpers: quality & validation
    # ---------------------------
    def _safe_text(self, s: str) -> str:
        """Unicode-safe normalization; keep symbols (±, μ, etc.)."""
        return unicodedata.normalize("NFC", s)

    def _preextract_metadata(self, paper: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Deterministic regex-first extraction for doi, pmid, year, sample size."""
        meta = {
            "id": paper.get("id"),
            "title": paper.get("title"),
            "doi": paper.get("doi"),
            "pmid": paper.get("pmid"),
            "journal": paper.get("journal"),
            "year": paper.get("year"),
            "url_pub": paper.get("url_pub"),
        }
        hay = " ".join([str(x) for x in [paper.get("content",""), paper.get("summary",""), text] if x])
        try:
            if not meta.get("doi"):
                m = re.search(r'\b10\.\d{4,9}/\S+\b', hay)
                if m: meta["doi"] = m.group(0).rstrip('.,;)')
            if not meta.get("pmid"):
                m = re.search(r'\bPMID[:\s]*([0-9]{4,9})\b', hay, flags=re.I)
                if m: meta["pmid"] = m.group(1)
            if not meta.get("year"):
                m = re.search(r'\b(19|20)\d{2}\b', hay)
                if m: meta["year"] = int(m.group(0))
            # sample size (very rough): n=24 or (n = 24) or "24 participants"
            m = re.search(r'\b[nN]\s*=\s*([0-9]{1,4})\b', hay)
            if m: meta["sample_size_hint"] = int(m.group(1))
        except Exception:
            pass
        return meta

    def _attach_evidence_spans(self, data: Dict[str, Any], source_text: str) -> None:
        """Attach simple evidence spans by finding sentences that mention the measure."""
        if not source_text:
            return
        text = self._safe_text(source_text)
        # naive sentence split
        sentences = re.split(r'(?<=[\.\?\!])\s+', text)
        def find_span(needle: str) -> Tuple[str, int, int]:
            if not needle: return ("", -1, -1)
            for s in sentences:
                if needle.lower() in s.lower():
                    start = text.find(s)
                    return (s, start, start+len(s))
            return ("", -1, -1)
        om = data.get("outcome_measures")
        if isinstance(om, dict):
            for dom, items in om.items():
                if isinstance(items, list):
                    for it in items:
                        meas = (it or {}).get("measure")
                        ev, a, b = find_span(meas) if meas else ("", -1, -1)
                        if ev:
                            it["evidence_text"] = ev
                            it["evidence_char_start"] = a
                            it["evidence_char_end"] = b
        # safety counts evidence
        sd = data.get("safety_data", {})
        if isinstance(sd, dict):
            ev, a, b = find_span("adverse")
            if ev:
                sd["evidence_text"] = ev
                sd["evidence_char_start"] = a
                sd["evidence_char_end"] = b

    def _coerce_stats_fields(self, data: Dict[str, Any]) -> None:
        """Ensure dual numeric/text fields for p-values and CIs exist where possible."""
        def parse_p(v) -> Tuple[Optional[float], Optional[str]]:
            if v is None: return (None, None)
            if isinstance(v, (int, float)): return (float(v), str(v))
            s = str(v).strip()
            m = re.search(r'([<>]=?)\s*0?\.(\d+)', s)
            if m:
                sym, dec = m.groups()
                num = float("0."+dec)
                return (num, s)
            m2 = re.search(r'\b0?\.(\d+)\b', s)
            if m2:
                num = float("0."+m2.group(1))
                return (num, s)
            return (None, s)
        def coerce_ci(obj: Dict[str, Any]) -> None:
            ci = obj.get("confidence_interval")
            ci_text = obj.get("ci_text")
            if isinstance(ci, list) and len(ci) == 2:
                # keep numeric list, ensure text present
                if not ci_text:
                    obj["ci_text"] = f"[{ci[0]}, {ci[1]}]"
            elif isinstance(ci, str):
                s = ci
                m = re.search(r'[-\[]\s*([\-+]?\d*\.?\d+)\s*[,;]\s*([\-+]?\d*\.?\d+)\s*[\]\)]', s)
                if m:
                    lo, hi = float(m.group(1)), float(m.group(2))
                    obj["confidence_interval"] = [lo, hi]
                    obj["ci_text"] = s
        om = data.get("outcome_measures")
        if isinstance(om, dict):
            for _, items in om.items():
                if isinstance(items, list):
                    for it in items:
                        # p-value fields
                        pv_num, pv_txt = parse_p(it.get("p_value") if "p_value" in it else it.get("p_value_text"))
                        if pv_txt and "p_value_text" not in it:
                            it["p_value_text"] = pv_txt
                        if pv_num is not None:
                            it["p_value_num"] = pv_num
                        coerce_ci(it)
        # safety: coerce counts if they look like "8%"
        sd = data.get("safety_data")
        if isinstance(sd, dict):
            ae = sd.get("adverse_events")
            if isinstance(ae, str) and ae.endswith("%"):
                try:
                    sd["adverse_events_percent"] = float(ae.strip("%"))
                except Exception:
                    pass

    def _validate_against_schema(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate minimal shape to catch obvious type issues."""
        if jsonschema_validate is None:
            return (True, None)
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": ["string","null"]},
                "title": {"type": ["string","null"]},
                "journal": {"type": ["string","null"]},
                "year": {"type": ["integer","string","null"]},
                "study_type": {"type": ["string","null"]},
                "outcome_measures": {"type": ["object","array","null"]},
                "safety_data": {"type": ["object","null"]},
                "dosage": {"type": ["object","null"]},
                "quality_scores": {"type": ["object","null"]},
                "context": {"type": ["object","null"]},
                "search_terms": {"type": ["array","null"]},
                "relevance_scores": {"type": ["object","null"]},
                "summary": {"type": ["string","null"]},
                "key_findings": {"type": ["array","null"]},
                "evidence_grade": {"type": ["string","null"]},
                "schema_version": {"type": ["string","null"]}
            },
            # Keep required list minimal to reduce false negatives
            "required": ["title", "journal"]
        }
        try:
            jsonschema_validate(instance=data, schema=schema)
            return (True, None)
        except JSONSchemaValidationError as e:
            return (False, str(e))

    def _build_repair_prompt(self, bad_obj: Dict[str, Any], err_msg: str) -> str:
        return (
            "<s>[INST] You returned JSON that failed schema validation. "
            "Fix ONLY types/missing fields; do not add new content. "
            "Return JSON only, no fences. Error:\n"
            f"{err_msg}\n\n"
            "JSON to fix:\n"
            f"{json.dumps(bad_obj, ensure_ascii=False)}\n[/INST]"
        )

    def _repair_with_model(self, prompt: str) -> Optional[Dict[str, Any]]:
        """One tiny repair pass with the same model; returns fixed dict or None."""
        device = next(self.model.parameters()).device
        enc = self._fit_inputs([prompt])
        input_ids = enc["input_ids"].to(device)
        attention_mask = enc["attention_mask"].to(device)
        stop_criteria = StoppingCriteriaList([StopOnSentinel(self.tokenizer, self.config.json_stop)])
        with torch.no_grad():
            out = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=256,
                do_sample=False,
                temperature=0.0,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                stopping_criteria=stop_criteria,
            )[0]
        src_len = input_ids[0].shape[0]
        resp = self.tokenizer.decode(out[src_len:], skip_special_tokens=True)
        resp = self._safe_text(resp)
        if self.config.json_stop in resp:
            resp = resp.split(self.config.json_stop, 1)[0]
        last = resp.rfind("}")
        if last != -1:
            resp = resp[:last+1]
        try:
            return json.loads(resp)
        except Exception:
            return None

    def _fill_required_defaults(self, d: Dict[str, Any]) -> None:
        """Populate minimally required fields to avoid failing on Nones."""
        d.setdefault("id", None)
        d.setdefault("title", None)
        d.setdefault("journal", None)
        # Normalize year to int where possible
        try:
            if isinstance(d.get("year"), str) and d["year"].isdigit():
                d["year"] = int(d["year"])
        except Exception:
            pass
        d.setdefault("study_type", None)
        d.setdefault("schema_version", self.config.schema_version)
        # Ensure nested blocks exist
        if "outcome_measures" not in d or not isinstance(d.get("outcome_measures"), (dict, list)):
            d["outcome_measures"] = {"strength": [], "endurance": [], "power": []}
        if isinstance(d["outcome_measures"], list):
            # Normalize list-of-items with "domain" to dict-of-arrays
            grouped = {}
            for item in d["outcome_measures"]:
                if isinstance(item, dict):
                    dom = str(item.get("domain", "unknown")).lower()
                    grouped.setdefault(dom, []).append(item)
            d["outcome_measures"] = grouped
        d.setdefault("safety_data", {})
        if isinstance(d["safety_data"], dict):
            d["safety_data"].setdefault("adverse_events", None)
            d["safety_data"].setdefault("serious_adverse_events", None)
            d["safety_data"].setdefault("dropouts", None)
        d.setdefault("dosage", {})
        d.setdefault("quality_scores", {})
        d.setdefault("context", {})
        d.setdefault("search_terms", [])
        d.setdefault("relevance_scores", {})
        d.setdefault("summary", None)
        d.setdefault("key_findings", [])
        d.setdefault("evidence_grade", None)
