from typing import Optional, List, Dict, Any
import json
import os
import time

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
try:
    from transformers import BitsAndBytesConfig  # for 4-bit quant
except Exception:
    BitsAndBytesConfig = None  # type: ignore


class MistralClient:
    def __init__(
        self,
        model_name: str = "mistralai/Mistral-7B-Instruct-v0.3",
        device: Optional[str] = None,
        quant_4bit: Optional[bool] = None,
    ):
        """
        Default: 4-bit NF4 on CUDA (optimal for RTX 3080).
        Override with env:
          EVIDENTFIT_QUANT_4BIT=0 to disable
          EVIDENTFIT_ATTN_IMPL=eager|flash_attention_2
          EVIDENTFIT_MODEL=<hf_repo_or_path>
        """
        self.model_name = os.environ.get("EVIDENTFIT_MODEL", model_name)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        hf_token = os.environ.get("HF_TOKEN")  # optional
        _auth = {"token": hf_token} if hf_token else {}

        # Local-only mode if model path is a directory, or env requests it
        import os as _os
        local_path = _os.path.isdir(self.model_name)
        local_only_env = _os.environ.get("EVIDENTFIT_LOCAL_ONLY") == "1"
        _local_kw = {"local_files_only": True} if (local_path or local_only_env) else {}

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, use_fast=True, **_auth, **_local_kw
        )

        # Quantization defaults
        env_q = os.environ.get("EVIDENTFIT_QUANT_4BIT")
        use_4bit = quant_4bit if quant_4bit is not None else (env_q is None or env_q == "1")

        # Attention implementation
        attn_impl_env = os.environ.get("EVIDENTFIT_ATTN_IMPL", "flash_attention_2")
        attn_impl = attn_impl_env if self.device == "cuda" else "eager"

        # Dtype (new API prefers `dtype`; we add a compat fallback below)
        _dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        model_kwargs: Dict[str, Any] = dict(
            dtype=_dtype,
            low_cpu_mem_usage=True,
            attn_implementation=attn_impl,
            device_map="auto",
        )

        if self.device == "cuda" and use_4bit and BitsAndBytesConfig is not None:
            try:
                model_kwargs.update(
                    dict(
                        quantization_config=BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_use_double_quant=True,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_compute_dtype=torch.bfloat16,
                        )
                    )
                )
            except Exception as e:
                # bnb/transformers mismatch or bnb not compiled; fall back safely
                print("[mistral_client] 4-bit setup failed, falling back to non-quantized:", repr(e))
                pass

        try:
            # Newer transformers expect `dtype=...`
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, **model_kwargs, **_auth, **_local_kw
            )
        except TypeError:
            # 1) Some builds don't accept `attn_implementation`
            model_kwargs.pop("attn_implementation", None)
            try:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name, **model_kwargs, **_auth, **_local_kw
                )
            except TypeError:
                # 2) Very old transformers expect `torch_dtype` instead of `dtype`
                model_kwargs.pop("dtype", None)
                model_kwargs["torch_dtype"] = _dtype
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name, **model_kwargs, **_auth, **_local_kw
                )

        # Tiny runtime log so we know what we’re using
        _attn = attn_impl if "attn_implementation" in model_kwargs or attn_impl_env else "eager"
        _quant = "4-bit NF4" if ("quantization_config" in model_kwargs) else "fp16/bf16"
        print(f"[mistral_client] loaded {self.model_name} with {_quant}, attn={_attn}, device={self.model.device}")

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{user_prompt} [/INST]"
        with torch.no_grad():
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            gen = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=temperature > 0.0,
                temperature=temperature,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            text = self.tokenizer.decode(gen[0], skip_special_tokens=True)
        # naive JSON slice
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            payload = json.loads(text[start:end])
            return payload
        except Exception:
            return {}


