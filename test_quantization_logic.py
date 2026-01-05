#!/usr/bin/env python3
"""Test the quantization logic to see what's happening"""

import os

def test_quantization_logic():
    """Test the exact logic from mistral_client.py"""
    
    # Test case 1: Default (no env vars set)
    print("=== Test Case 1: Default (no env vars) ===")
    os.environ.pop("EVIDENTFIT_QUANT_4BIT", None)
    os.environ.pop("EVIDENTFIT_QUANT_8BIT", None)
    
    env_q = os.environ.get("EVIDENTFIT_QUANT_4BIT")
    use_4bit = env_q != "0"  # Default to True
    env_8bit = os.environ.get("EVIDENTFIT_QUANT_8BIT", "0")
    use_8bit = env_8bit == "1"
    use_8bit_offload = env_8bit == "offload"
    
    if use_8bit or use_8bit_offload:
        use_4bit = False
    
    print(f"EVIDENTFIT_QUANT_4BIT: {env_q}")
    print(f"EVIDENTFIT_QUANT_8BIT: {env_8bit}")
    print(f"use_4bit: {use_4bit}")
    print(f"use_8bit: {use_8bit}")
    print(f"use_8bit_offload: {use_8bit_offload}")
    
    # Test case 2: 4-bit enabled
    print("\n=== Test Case 2: 4-bit enabled ===")
    os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
    os.environ["EVIDENTFIT_QUANT_8BIT"] = "0"
    
    env_q = os.environ.get("EVIDENTFIT_QUANT_4BIT")
    use_4bit = env_q != "0"  # Default to True
    env_8bit = os.environ.get("EVIDENTFIT_QUANT_8BIT", "0")
    use_8bit = env_8bit == "1"
    use_8bit_offload = env_8bit == "offload"
    
    if use_8bit or use_8bit_offload:
        use_4bit = False
    
    print(f"EVIDENTFIT_QUANT_4BIT: {env_q}")
    print(f"EVIDENTFIT_QUANT_8BIT: {env_8bit}")
    print(f"use_4bit: {use_4bit}")
    print(f"use_8bit: {use_8bit}")
    print(f"use_8bit_offload: {use_8bit_offload}")
    
    # Test case 3: 8-bit enabled
    print("\n=== Test Case 3: 8-bit enabled ===")
    os.environ["EVIDENTFIT_QUANT_4BIT"] = "1"
    os.environ["EVIDENTFIT_QUANT_8BIT"] = "1"
    
    env_q = os.environ.get("EVIDENTFIT_QUANT_4BIT")
    use_4bit = env_q != "0"  # Default to True
    env_8bit = os.environ.get("EVIDENTFIT_QUANT_8BIT", "0")
    use_8bit = env_8bit == "1"
    use_8bit_offload = env_8bit == "offload"
    
    if use_8bit or use_8bit_offload:
        use_4bit = False
    
    print(f"EVIDENTFIT_QUANT_4BIT: {env_q}")
    print(f"EVIDENTFIT_QUANT_8BIT: {env_8bit}")
    print(f"use_4bit: {use_4bit}")
    print(f"use_8bit: {use_8bit}")
    print(f"use_8bit_offload: {use_8bit_offload}")

if __name__ == "__main__":
    test_quantization_logic()
