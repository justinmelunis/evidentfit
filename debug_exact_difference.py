#!/usr/bin/env python3
"""Debug the exact difference between working and failing code"""

import os
import sys
import torch
import time
import json
from pathlib import Path

def get_gpu_memory():
    """Get current GPU memory usage"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024**3
    return 0

def log_memory(step_name):
    """Log current memory usage"""
    mem = get_gpu_memory()
    print(f"[{step_name}] GPU Memory: {mem:.2f} GB")

def test_working_version():
    """Test the version that works (isolated)"""
    print("=" * 60)
    print("TESTING WORKING VERSION (ISOLATED)")
    print("=" * 60)
    
    # Set up environment for 4-bit quantization
    os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
    os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"
    
    # Clear GPU memory
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    log_memory("START")
    
    try:
        # Add the agents/paper_processor directory to the path
        sys.path.insert(0, 'agents/paper_processor')
        
        print("Loading model...")
        from mistral_client import MistralClient
        client = MistralClient(model_name="E:/models/Mistral-7B-Instruct-v0.3")
        
        log_memory("After model load")
        print("SUCCESS: WORKING VERSION SUCCESS")
        return True
        
    except Exception as e:
        print(f"FAILED: WORKING VERSION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_failing_version():
    """Test the version that fails (paper processor context)"""
    print("\n" + "=" * 60)
    print("TESTING FAILING VERSION (PAPER PROCESSOR CONTEXT)")
    print("=" * 60)
    
    # Set up environment exactly like paper processor
    os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
    os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"
    os.environ['EVIDENTFIT_DB_DSN'] = 'postgresql://postgres:Winston8891**@localhost:5432/evidentfit'
    
    # Clear GPU memory
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    log_memory("START")
    
    try:
        # Add the agents/paper_processor directory to the path
        sys.path.insert(0, 'agents/paper_processor')
        
        # Step 1: Load meta_map (this is what paper processor does first)
        print("Loading meta_map...")
        from collect import _load_meta_map
        canonical_path = Path("E:/Git/evidentfit/data/index/canonical_papers.jsonl")
        meta_map = _load_meta_map(canonical_path)
        print(f"Loaded {len(meta_map)} papers")
        log_memory("After meta_map load")
        
        # Step 2: Import all modules that paper processor imports
        print("Importing all paper processor modules...")
        from collect import build_section_bundle
        from extract import extract_from_bundle
        from schema import normalize_data, create_dedupe_key, validate_optimized_schema
        from validation import validate_card, log_validation_results
        from db_writer import write_card_to_db
        from storage_manager import StorageManager
        from logging_config import setup_logging
        print("All modules imported")
        log_memory("After importing all modules")
        
        # Step 3: Now try to load the model (this is where it fails)
        print("Loading model...")
        from mistral_client import MistralClient
        client = MistralClient(model_name="E:/models/Mistral-7B-Instruct-v0.3")
        
        log_memory("After model load")
        print("SUCCESS: FAILING VERSION SUCCESS")
        return True
        
    except Exception as e:
        print(f"FAILED: FAILING VERSION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def compare_environment():
    """Compare the environment between working and failing versions"""
    print("\n" + "=" * 60)
    print("ENVIRONMENT COMPARISON")
    print("=" * 60)
    
    print("Environment variables:")
    for key, value in os.environ.items():
        if 'EVIDENTFIT' in key or 'CUDA' in key or 'TORCH' in key:
            print(f"  {key}: {value}")
    
    print(f"\nPython path:")
    for i, path in enumerate(sys.path):
        if 'agents' in path or 'evidentfit' in path.lower():
            print(f"  {i}: {path}")
    
    print(f"\nTorch CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device count: {torch.cuda.device_count()}")
        print(f"Current device: {torch.cuda.current_device()}")
        print(f"Device name: {torch.cuda.get_device_name()}")

if __name__ == "__main__":
    print("DEBUGGING EXACT DIFFERENCE BETWEEN WORKING AND FAILING CODE")
    print("=" * 80)
    
    # Compare environments first
    compare_environment()
    
    # Test working version
    working_success = test_working_version()
    
    # Test failing version
    failing_success = test_failing_version()
    
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"Working version: {'SUCCESS' if working_success else 'FAILED'}")
    print(f"Failing version: {'SUCCESS' if failing_success else 'FAILED'}")
    
    if working_success and not failing_success:
        print("\nDIFFERENCE FOUND: The issue is in the paper processor context!")
    elif working_success and failing_success:
        print("\nBOTH WORK: The issue might be elsewhere...")
    else:
        print("\nBOTH FAIL: The issue is fundamental...")
