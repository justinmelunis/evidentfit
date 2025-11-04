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

        # Quantization defaults - 4-bit is default for RTX 3080
        env_q = os.environ.get("EVIDENTFIT_QUANT_4BIT")
        use_4bit = quant_4bit if quant_4bit is not None else (env_q != "0")  # Default to True
        
        # Check for 8-bit quantization
        env_8bit = os.environ.get("EVIDENTFIT_QUANT_8BIT", "0")
        use_8bit = env_8bit == "1"
        use_8bit_offload = env_8bit == "offload"
        
        # If 8-bit is enabled, disable 4-bit
        if use_8bit or use_8bit_offload:
            use_4bit = False

        # Attention implementation - try flash_attention_2, then sdpa, then eager
        attn_impl_env = os.environ.get("EVIDENTFIT_ATTN_IMPL", "flash_attention_2")
        if self.device == "cuda" and attn_impl_env == "flash_attention_2":
            try:
                import flash_attn
                attn_impl = "flash_attention_2"
                print("[mistral_client] Using flash_attention_2")
            except ImportError:
                print("[mistral_client] flash_attention_2 not available, trying sdpa")
                attn_impl = "sdpa"
        elif self.device == "cuda" and attn_impl_env == "sdpa":
            attn_impl = "sdpa"
            print("[mistral_client] Using sdpa")
        else:
            attn_impl = "eager"
            print("[mistral_client] Using eager attention")

        # Dtype (new API prefers `dtype`; we add a compat fallback below)
        _dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        # Use auto device mapping for quantization modes
        if use_4bit or use_8bit or use_8bit_offload:
            device_map = "auto"
        else:
            device_map = "cuda:0" if self.device == "cuda" else "cpu"
        
        model_kwargs: Dict[str, Any] = dict(
            low_cpu_mem_usage=True,
            attn_implementation=attn_impl,
            device_map=device_map,
        )
        
        # Only set dtype when NOT using quantization (quantization manages its own dtypes)
        if not (use_4bit or use_8bit or use_8bit_offload):
            model_kwargs["dtype"] = _dtype

        if self.device == "cuda" and use_8bit and BitsAndBytesConfig is not None:
            try:
                model_kwargs.update(
                    dict(
                        quantization_config=BitsAndBytesConfig(
                            load_in_8bit=True,
                            llm_int8_enable_fp32_cpu_offload=False,  # Pure GPU, no offloading
                        )
                    )
                )
                print("[mistral_client] Using 8-bit quantization (GPU-only)")
            except Exception as e:
                print("[mistral_client] 8-bit setup failed, falling back to non-quantized:", repr(e))
                pass
        elif self.device == "cuda" and use_8bit_offload and BitsAndBytesConfig is not None:
            try:
                model_kwargs.update(
                    dict(
                        quantization_config=BitsAndBytesConfig(
                            load_in_8bit=True,
                            llm_int8_enable_fp32_cpu_offload=True,  # Allow CPU offloading
                        )
                    )
                )
                print("[mistral_client] Using 8-bit quantization with CPU offloading")
            except Exception as e:
                print("[mistral_client] 8-bit offload setup failed, falling back to non-quantized:", repr(e))
                pass
        elif self.device == "cuda" and use_4bit and BitsAndBytesConfig is not None:
            try:
                print("[mistral_client] Setting up 4-bit quantization...")
                model_kwargs.update(
                    dict(
                        quantization_config=BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_use_double_quant=True,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_compute_dtype=torch.float16,  # Try float16 instead of bfloat16
                            bnb_4bit_quant_storage=torch.uint8,    # More stable storage
                        )
                    )
                )
                print("[mistral_client] 4-bit quantization config added successfully")
            except Exception as e:
                # bnb/transformers mismatch or bnb not compiled; fall back safely
                print("[mistral_client] 4-bit setup failed, falling back to non-quantized:", repr(e))
                pass

        try:
            # Newer transformers expect `dtype=...`
            print(f"[mistral_client] Loading model with kwargs: {list(model_kwargs.keys())}")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, **model_kwargs, **_auth, **_local_kw
            )
            print("[mistral_client] Model loaded successfully with first attempt")
        except TypeError as e:
            print(f"[mistral_client] First load attempt failed with TypeError: {e}")
            # 1) Some builds don't accept `attn_implementation`
            # Save quantization config before removing attn_implementation
            quantization_config = model_kwargs.pop("quantization_config", None)
            model_kwargs.pop("attn_implementation", None)
            if quantization_config:
                model_kwargs["quantization_config"] = quantization_config
            try:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name, **model_kwargs, **_auth, **_local_kw
                )
                print("[mistral_client] Model loaded successfully with second attempt")
            except TypeError as e2:
                print(f"[mistral_client] Second load attempt failed with TypeError: {e2}")
                # 2) Very old transformers expect `torch_dtype` instead of `dtype`
                # Save quantization config before removing dtype
                quantization_config = model_kwargs.pop("quantization_config", None)
                model_kwargs.pop("dtype", None)
                # Only set torch_dtype if NOT using quantization
                if not quantization_config:
                    model_kwargs["torch_dtype"] = _dtype
                if quantization_config:
                    model_kwargs["quantization_config"] = quantization_config
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name, **model_kwargs, **_auth, **_local_kw
                )
                print("[mistral_client] Model loaded successfully with third attempt")
        except Exception as e:
            print(f"[mistral_client] Model loading failed with unexpected error: {e}")
            raise

        # Tiny runtime log so we know what we're using
        _attn = attn_impl if "attn_implementation" in model_kwargs or attn_impl_env else "eager"
        if "quantization_config" in model_kwargs:
            _quant = "8-bit" if use_8bit else "4-bit NF4"
            print(f"[mistral_client] Quantization config was applied: {model_kwargs['quantization_config']}")
        else:
            _quant = "fp16/bf16"
            print(f"[mistral_client] WARNING: No quantization config found in model_kwargs!")
        print(f"[mistral_client] loaded {self.model_name} with {_quant}, attn={_attn}, device={self.model.device}")
        
        # Check if model is actually quantized
        if hasattr(self.model, 'is_quantized') and self.model.is_quantized:
            print(f"[mistral_client] Model is confirmed to be quantized: {self.model.is_quantized}")
        else:
            print(f"[mistral_client] WARNING: Model does not appear to be quantized!")

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

    def generate_batch_json(
        self,
        system_prompt: str,
        user_prompts: List[str],
        max_new_tokens: int = 512,
        temperature: float = 0.0,
        batch_size: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Process multiple prompts in batches for better GPU utilization.
        Returns a list of JSON objects, one per input prompt.
        """
        results = []
        
        for i in range(0, len(user_prompts), batch_size):
            batch_prompts = user_prompts[i:i + batch_size]
            batch_results = []
            
            # Prepare batch inputs
            batch_texts = []
            for user_prompt in batch_prompts:
                prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{user_prompt} [/INST]"
                batch_texts.append(prompt)
            
            with torch.no_grad():
                # Tokenize batch
                inputs = self.tokenizer(
                    batch_texts, 
                    return_tensors="pt", 
                    padding=True, 
                    truncation=True,
                    max_length=16384  # Reasonable limit
                ).to(self.model.device)
                
                # Generate for batch
                gen = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=temperature > 0.0,
                    temperature=temperature,
                    pad_token_id=self.tokenizer.eos_token_id,
                    use_cache=True,
                )
                
                # Decode each result
                for j, generated_ids in enumerate(gen):
                    # Remove input tokens to get only generated text
                    input_length = inputs['input_ids'][j].shape[0]
                    generated_text = self.tokenizer.decode(
                        generated_ids[input_length:], 
                        skip_special_tokens=True
                    )
                    
                    # Extract JSON
                    try:
                        start = generated_text.index("{")
                        end = generated_text.rindex("}") + 1
                        payload = json.loads(generated_text[start:end])
                        batch_results.append(payload)
                    except Exception:
                        batch_results.append({})
            
            results.extend(batch_results)
            
            # Clear cache between batches to manage memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        return results


