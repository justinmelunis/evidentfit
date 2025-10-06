from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import logging
import re

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
try:
    from transformers import BitsAndBytesConfig
except Exception:
    BitsAndBytesConfig = None  # optional

from schema import create_optimized_prompt, normalize_data, create_dedupe_key

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

        quant_args = {}
        if self.cfg.use_4bit and BitsAndBytesConfig is not None:
            quant_args["load_in_4bit"] = True
            quant_args["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
        self.tokenizer = AutoTokenizer.from_pretrained(self.cfg.model_name, use_fast=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.cfg.model_name,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map=self.cfg.device_map if self.device == "cuda" else None,
            **quant_args
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        # try to locate a top-level JSON object
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
        raw = text[start:end]
        raw = raw.replace(",}", "}").replace(",]", "]")
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _postprocess(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        obj = normalize_data(obj)
        obj.setdefault("dedupe_key", create_dedupe_key(obj))
        obj.setdefault("schema_version", self.cfg.schema_version)
        return obj

    def generate_batch_summaries(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []
        for p in papers:
            prompt = create_optimized_prompt(p)

            enc = self.tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=self.cfg.ctx_tokens
            )
            for k in enc:
                enc[k] = enc[k].to(self.model.device)

            with torch.inference_mode():
                gen = self.model.generate(
                    **enc,
                    do_sample=False if self.cfg.temperature <= 0.0 else True,
                    temperature=max(self.cfg.temperature, 1e-5),
                    max_new_tokens=self.cfg.max_new_tokens,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
            out_text = self.tokenizer.decode(gen[0], skip_special_tokens=True)

            # Heuristic: only keep the model's completion after the prompt
            if out_text.startswith(prompt):
                out_text = out_text[len(prompt):].strip()

            obj = self._extract_json(out_text) or {}
            if not obj:
                # minimal fallback
                obj = {
                    "id": p.get("id") or p.get("pmid") or p.get("doi") or "unknown",
                    "title": p.get("title") or "Unknown Title",
                    "journal": p.get("journal") or "Unknown Journal",
                    "year": p.get("year") or None,
                    "pmid": p.get("pmid"),
                    "doi": p.get("doi"),
                    "summary": "Model output did not include valid JSON. Fallback entry.",
                    "key_findings": [],
                    "supplements": p.get("supplements", "").split(",") if p.get("supplements") else [],
                    "evidence_grade": "D",
                    "quality_score": 1.0,
                }
            outputs.append(self._postprocess(obj))
        return outputs
