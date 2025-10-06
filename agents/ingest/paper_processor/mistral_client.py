from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import logging
import os

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
try:
    from transformers import BitsAndBytesConfig
except Exception:
    BitsAndBytesConfig = None  # optional

from schema import (
    create_optimized_prompt,
    create_repair_prompt,
    normalize_data,
    create_dedupe_key,
    REQUIRED_FIELDS,
    validate_optimized_schema,
)

LOG = logging.getLogger(__name__)

@dataclass
class ProcessingConfig:
    model_name: str
    ctx_tokens: int
    max_new_tokens: int
    temperature: float
    batch_size: int
    microbatch_size: int
    use_4bit: bool
    device_map: str
    enable_schema_validation: bool
    enable_model_repair: bool
    schema_version: str = "v1.2"

class MistralClient:
    def __init__(self, cfg: ProcessingConfig):
        self.cfg = cfg
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        torch.set_grad_enabled(False)
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True

        quant_args = {}
        if self.cfg.use_4bit and BitsAndBytesConfig is not None:
            quant_args["load_in_4bit"] = True
            quant_args["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float16,
            )

        attn_impl = os.environ.get("EF_ATTN_IMPL", "flash_attention_2")
        dtype = torch.bfloat16 if (self.device == "cuda") else torch.float32

        self.tokenizer = AutoTokenizer.from_pretrained(self.cfg.model_name, use_fast=True)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"
            
                self.model = AutoModelForCausalLM.from_pretrained(
            self.cfg.model_name,
            torch_dtype=dtype,
            device_map=self.cfg.device_map if self.device == "cuda" else None,
            low_cpu_mem_usage=True,
            attn_implementation=attn_impl,
            **quant_args
        )
        self.model.generation_config.use_cache = True
        self.model.generation_config.num_beams = 1
        self.model.generation_config.do_sample = (self.cfg.temperature > 0.0)

    # -----------------------------
    # Helpers
    # -----------------------------

    def _decode_completion(self, prompt: str, max_new: Optional[int] = None, temperature: Optional[float] = None) -> str:
        max_new = self.cfg.max_new_tokens if max_new is None else max_new
        temperature = self.cfg.temperature if temperature is None else temperature

        enc = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.cfg.ctx_tokens,
            padding=False,
        )
        for k in enc:
            enc[k] = enc[k].to(self.model.device)

        with torch.inference_mode():
                gen = self.model.generate(
                **enc,
                do_sample=(temperature > 0.0),
                temperature=max(temperature, 1e-5),
                max_new_tokens=max_new,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )
        out_text = self.tokenizer.decode(gen[0], skip_special_tokens=True)
        if out_text.startswith(prompt):
            out_text = out_text[len(prompt):].strip()
        return out_text

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        # find a top-level JSON object
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        end = -1
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            return None
        raw = text[start:end].replace(",}", "}").replace(",]", "]")
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _missing_fields(self, obj: Dict[str, Any]) -> List[str]:
        """Return keys that are absent or effectively empty."""
        missing = []
        for k, default in REQUIRED_FIELDS.items():
            if k not in obj:
                missing.append(k)
                continue
            v = obj.get(k)
            # consider empty string/whitespace, empty list, None as missing
            if isinstance(v, str) and not v.strip():
                missing.append(k)
            elif isinstance(v, list) and len(v) == 0:
                missing.append(k)
            elif v is None:
                missing.append(k)
        return missing

    def _merge_fill(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        """Fill only previously missing fields; never overwrite non-empty values."""
        out = dict(base)
        for k, v in (patch or {}).items():
            if k not in REQUIRED_FIELDS:
                continue
            if k not in out:
                out[k] = v
                continue
            cur = out[k]
            is_missing = (
                cur is None or
                (isinstance(cur, str) and not cur.strip()) or
                (isinstance(cur, list) and len(cur) == 0)
            )
            if is_missing:
                out[k] = v
        return out

    # -----------------------------
    # Public API
    # -----------------------------

    def generate_batch_summaries(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []

        for p in papers:
            # Pass 1: strict prompt, deterministic
            prompt = create_optimized_prompt(p)
            text = self._decode_completion(prompt, max_new=self.cfg.max_new_tokens, temperature=0.0)
            obj = self._extract_json(text) or {}
            if not obj:
                # minimal fallback stub
                obj = {
                    "id": p.get("id") or p.get("pmid") or p.get("doi") or "unknown",
                    "title": p.get("title") or "unknown",
                    "journal": p.get("journal") or "unknown",
                    "year": p.get("year"),
                    "pmid": p.get("pmid"),
                    "doi": p.get("doi"),
                    "summary": "unknown",
                    "key_findings": [],
                    "supplements": [],
                    "evidence_grade": "D",
                    "quality_score": 0.0,
                    "study_type": "unknown",
                    "outcome_measures": {"strength": [], "endurance": [], "power": []},
                    "keywords": [],
                    "relevance_tags": [],
                }

            # Normalize once to set defaults
            obj = normalize_data(obj)

            # Targeted repair if important fields are missing
            missing = self._missing_fields(obj)
            if missing:
                try:
                    rp = create_repair_prompt(missing_fields=missing, prior_json=obj, paper=p)
                    # small repair budget; still deterministic
                    rtext = self._decode_completion(rp, max_new=min(256, self.cfg.max_new_tokens // 2), temperature=0.0)
                    robj = self._extract_json(rtext) or {}
                    if robj:
                        obj = self._merge_fill(obj, robj)
                        obj = normalize_data(obj)
                except Exception:
                    # Best-effort; keep first-pass result
                    pass

            # Final validation (do not discard; just log)
            if not validate_optimized_schema(obj):
                LOG.debug("validate_optimized_schema: object still missing non-critical keys after repair.")

            # Ensure id/dedupe present
            obj.setdefault("dedupe_key", create_dedupe_key(obj))
            outputs.append(obj)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return outputs
