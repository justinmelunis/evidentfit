#!/usr/bin/env python3
"""Test script to check Mistral model loading with quantization"""

import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# Set up environment for 4-bit quantization
os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"

print("=== Mistral Model Loading Test ===")
print(f"EVIDENTFIT_QUANT_4BIT: {os.environ.get('EVIDENTFIT_QUANT_4BIT')}")
print(f"EVIDENTFIT_QUANT_8BIT: {os.environ.get('EVIDENTFIT_QUANT_8BIT')}")

# Check GPU memory before loading
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    print(f"GPU memory before loading: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
    print(f"GPU memory reserved before loading: {torch.cuda.memory_reserved() / 1024**3:.2f} GB")

# Test with local Mistral model
model_name = "E:/models/Mistral-7B-Instruct-v0.3"

try:
    print(f"\nLoading tokenizer for {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    
    print("Setting up 4-bit quantization config...")
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_storage=torch.uint8,
    )
    
    print("Loading model with 4-bit quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        device_map="auto",
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    
    print("Model loaded successfully!")
    print(f"Model device: {model.device}")
    print(f"Model dtype: {model.dtype}")
    
    # Check GPU memory after loading
    if torch.cuda.is_available():
        print(f"GPU memory after loading: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
        print(f"GPU memory reserved after loading: {torch.cuda.memory_reserved() / 1024**3:.2f} GB")
    
    # Test a simple generation
    print("\nTesting generation...")
    prompt = "<s>[INST] Hello, how are you? [/INST]"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=20, do_sample=False)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"Generated: {response}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
