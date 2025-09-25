#!/usr/bin/env python3
"""
Test script for Azure AI Foundry integration
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("🔍 Testing Azure AI Foundry configuration...")
print(f"Endpoint: {os.getenv('AZURE_INFERENCE_ENDPOINT')}")
print(f"Chat Model: {os.getenv('AZURE_INFERENCE_CHAT_MODEL')}")
print(f"Embed Model: {os.getenv('AZURE_INFERENCE_EMBED_MODEL')}")

try:
    from inference_client import foundry_chat, foundry_embed
    print("✅ Foundry client imported successfully")
    
    # Test chat
    print("\n🧪 Testing chat completion...")
    response = foundry_chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Can you tell me what model you are?"}
        ],
        max_tokens=50,
        temperature=0.2
    )
    print(f"✅ Chat response: {response}")
    
    # Test embedding
    print("\n🧪 Testing embeddings...")
    embeddings = foundry_embed(["test text"])
    print(f"✅ Embedding dimensions: {len(embeddings[0])}")
    
    print("\n🎉 All tests passed! Azure AI Foundry is working correctly.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
