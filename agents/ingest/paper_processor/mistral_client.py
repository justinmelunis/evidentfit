from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import logging
import re
import os

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
try:
    from transformers import BitsAndBytesConfig
except Exception:
    BitsAndBytesConfig = None  # optional

from schema import create_optimized_prompt, normalize_data, create_dedupe_key

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

        # VRAM-friendly flags
        torch.set_grad_enabled(False)
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True  # perf boost, no extra VRAM

        quant_args = {}
        if self.cfg.use_4bit and BitsAndBytesConfig is not None:
            quant_args["load_in_4bit"] = True
            quant_args["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float16,
            )

        attn_impl = os.environ.get("EF_ATTN_IMPL", "flash_attention_2")  # falls back to fa2 if built, else HF picks math/torch
        dtype = torch.bfloat16 if (self.device == "cuda") else torch.float32

        self.tokenizer = AutoTokenizer.from_pretrained(self.cfg.model_name, use_fast=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        # left padding helps when batching variable-length chunks; OK with batch=1 too
        self.tokenizer.padding_side = "left"

        self.model = AutoModelForCausalLM.from_pretrained(
            self.cfg.model_name,
            torch_dtype=dtype,
            device_map=self.cfg.device_map if self.device == "cuda" else None,
            low_cpu_mem_usage=True,
            attn_implementation=attn_impl,  # uses FA2 when available
            **quant_args
        )
        # Make sure generation config is VRAM-friendly
        self.model.generation_config.use_cache = True
        self.model.generation_config.num_beams = 1  # no beam search
        self.model.generation_config.do_sample = (self.cfg.temperature > 0.0)

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

        # We keep effective batch ~1 to cap VRAM; this loop can be batched later if you want the tradeoff.
        for p in papers:
            prompt = create_optimized_prompt(p)

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
                    do_sample=(self.cfg.temperature > 0.0),
                    temperature=max(self.cfg.temperature, 1e-5),
                    max_new_tokens=self.cfg.max_new_tokens,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    use_cache=True,
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

            # Release small caches between items to reduce fragmentation
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return outputs
