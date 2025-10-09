from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import json
import logging
import os
import math

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
    seed: Optional[int] = None

class MistralClient:
    def __init__(self, cfg: ProcessingConfig):
        self.cfg = cfg
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Global seeding for reproducibility (optional)
        _seed = self.cfg.seed
        try:
            _seed = int(os.environ.get("EF_SEED", _seed)) if os.environ.get("EF_SEED") is not None else _seed
        except Exception:
            pass
        if _seed is not None:
            import random, numpy as np
            random.seed(_seed)
            np.random.seed(_seed)
            torch.manual_seed(_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(_seed)
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False

        torch.set_grad_enabled(False)
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True

        quant_args = {}
        if self.cfg.use_4bit and BitsAndBytesConfig is not None:
            # Only pass quantization_config; do NOT also pass load_in_4bit kwarg
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
        # Left padding improves packing for variable-length prompts
        self.tokenizer.padding_side = "left"

        self.model = AutoModelForCausalLM.from_pretrained(
            self.cfg.model_name,
            dtype=dtype,
            device_map=self.cfg.device_map if self.device == "cuda" else None,
            low_cpu_mem_usage=True,
            attn_implementation=attn_impl,
            **quant_args
        )
        self.model.generation_config.use_cache = True
        self.model.generation_config.num_beams = 1
        # Keep deterministic by default; we set do_sample per-call
        self.model.generation_config.do_sample = False

        # Token budget for adaptive batching
        self.tokens_per_batch_target = int(os.environ.get("EF_TOKENS_PER_BATCH", "12000"))
        # Safety floor so one large prompt still runs
        self.tokens_per_batch_min = max(2048, int(self.tokens_per_batch_target * 0.5))

    # -----------------------------
    # JSON helpers
    # -----------------------------

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
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
        missing = []
        for k, _default in REQUIRED_FIELDS.items():
            if k not in obj:
                missing.append(k); continue
            v = obj.get(k)
            if v is None:
                missing.append(k); continue
            if isinstance(v, str) and not v.strip():
                missing.append(k); continue
            if isinstance(v, list) and len(v) == 0:
                missing.append(k); continue
        return missing

    def _merge_fill(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(base)
        for k, v in (patch or {}).items():
            if k not in REQUIRED_FIELDS:
                continue
            cur = out.get(k)
            is_missing = (
                cur is None or
                (isinstance(cur, str) and not cur.strip()) or
                (isinstance(cur, list) and len(cur) == 0)
            )
            if is_missing:
                out[k] = v
        return out

    # -----------------------------
    # Token estimation / packing
    # -----------------------------

    def _prompt_tokens(self, prompt: str) -> int:
        # Exact token length with truncation to context
        enc = self.tokenizer(prompt, return_tensors=None, add_special_tokens=True)
        return min(len(enc["input_ids"]), self.cfg.ctx_tokens)

    def _pack_batches(self, prompts: List[str]) -> List[List[Tuple[int, str]]]:
        """
        Pack prompts into batches under a token budget.
        Returns list of batches; each batch is [(idx, prompt), ...]
        """
        batches: List[List[Tuple[int, str]]] = []
        current: List[Tuple[int, str]] = []
        cur_tokens = 0

        for idx, pr in enumerate(prompts):
            t = self._prompt_tokens(pr)
            req_tokens = t + self.cfg.max_new_tokens  # rough total token load
            # If adding this item exceeds budget or batch size, flush current
            if current and ((cur_tokens + req_tokens > self.tokens_per_batch_target) or (len(current) >= max(1, self.cfg.batch_size))):
                batches.append(current)
                current = []
                cur_tokens = 0

            # If single item itself exceeds target but below hard floor, allow it alone
            if req_tokens > self.tokens_per_batch_target and req_tokens <= (self.tokens_per_batch_target + self.cfg.max_new_tokens):
                batches.append([(idx, pr)])
                continue

            # If it's too big even for floor, we still put it alone; generation will truncate to ctx
            if req_tokens > self.tokens_per_batch_target and not current:
                batches.append([(idx, pr)])
                continue

            current.append((idx, pr))
            cur_tokens += req_tokens

        if current:
            batches.append(current)

        return batches

    # -----------------------------
    # Decoding
    # -----------------------------

    def _decode_batch(self, batch_prompts: List[str], temperature: float, max_new: int) -> List[str]:
        # Tokenize with left padding to max length in batch
        enc = self.tokenizer(
            batch_prompts,
            return_tensors="pt",
            truncation=True,
            max_length=self.cfg.ctx_tokens,
            padding=True,  # left padding previously set
        )
        for k in enc:
            enc[k] = enc[k].to(self.model.device)

        # Deterministic by default unless temperature > 0
        do_sample = temperature > 0.0
        try:
            with torch.inference_mode():
                gen = self.model.generate(
                    **enc,
                    do_sample=do_sample,
                    temperature=max(temperature, 1e-5),
                    max_new_tokens=max_new,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    use_cache=True,
                )
        except torch.cuda.OutOfMemoryError:
            # Fallback: split batch and decode halves
            if len(batch_prompts) == 1:
                raise
            mid = math.ceil(len(batch_prompts) / 2)
            return self._decode_batch(batch_prompts[:mid], temperature, max_new) + \
                   self._decode_batch(batch_prompts[mid:], temperature, max_new)

        texts = self.tokenizer.batch_decode(gen, skip_special_tokens=True)
        # Strip the prompt prefix per item
        stripped = []
        for ptxt, out in zip(batch_prompts, texts):
            if out.startswith(ptxt):
                stripped.append(out[len(ptxt):].strip())
            else:
                stripped.append(out.strip())
        return stripped

    def _decode_single(self, prompt: str, temperature: float, max_new: int) -> str:
        return self._decode_batch([prompt], temperature, max_new)[0]

    # -----------------------------
    # Public API
    # -----------------------------

    def generate_batch_summaries(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Adaptive-batched generation:
          - First pass deterministic (temperature=0.0)
          - Pack into batches under a token budget (EF_TOKENS_PER_BATCH)
          - Parse/normalize each item
          - Targeted repair for missing fields (single-item deterministic pass)
        """
        outputs: List[Dict[str, Any]] = []
        if not papers:
            return outputs

        # Build prompts
        prompts = [create_optimized_prompt(p) for p in papers]
        batches = self._pack_batches(prompts)

        # Pass 1: deterministic, batched
        first_pass_objs: Dict[int, Dict[str, Any]] = {}
        for batch in batches:
            idxs = [i for i, _ in batch]
            pr_batch = [pr for _, pr in batch]
            texts = self._decode_batch(pr_batch, temperature=0.0, max_new=self.cfg.max_new_tokens)
            for i, out_text, pr in zip(idxs, texts, pr_batch):
                obj = self._extract_json(out_text) or {}
                if not obj:
                    # minimal fallback stub (valid JSON with defaults)
                    p = papers[i]
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
                obj = normalize_data(obj)
                first_pass_objs[i] = obj

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Targeted repair on items still missing fields (single-item deterministic)
        for i, base in first_pass_objs.items():
            missing = self._missing_fields(base)
            if not missing:
                outputs.append(self._finalize(base))
                continue

            try:
                rp = create_repair_prompt(missing_fields=missing, prior_json=base, paper=papers[i])
                rtext = self._decode_single(rp, temperature=0.0, max_new=min(256, self.cfg.max_new_tokens // 2))
                robj = self._extract_json(rtext) or {}
                if robj:
                    merged = self._merge_fill(base, robj)
                    merged = normalize_data(merged)
                    outputs.append(self._finalize(merged))
                else:
                    outputs.append(self._finalize(base))
            except Exception:
                outputs.append(self._finalize(base))

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Keep order aligned with input
        outputs_sorted = [outputs[idx] for idx in sorted(range(len(outputs)), key=lambda k: k)]
        return outputs_sorted

    # -----------------------------
    # Finalization
    # -----------------------------

    def _finalize(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        if not validate_optimized_schema(obj):
            LOG.debug("validate_optimized_schema: object missing non-critical keys after repair.")
        obj.setdefault("dedupe_key", create_dedupe_key(obj))
        obj.setdefault("schema_version", self.cfg.schema_version)
        return obj
