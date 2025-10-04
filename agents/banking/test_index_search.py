#!/usr/bin/env python3
"""
Test script to understand how supplements are stored in the index
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('banking_init.env')

# Try to use Key Vault for credentials (same as API)
try:
    sys.path.append('../../api')
    from keyvault_client import KeyVaultClient
    
    # Initialize Key Vault client
    kv_client = KeyVaultClient()
    
    # Get credentials from Key Vault
    foundation_endpoint = kv_client.get_secret("foundation-endpoint")
    foundation_key = kv_client.get_secret("foundation-key")
    
    if foundation_endpoint and foundation_key:
        os.environ["FOUNDATION_ENDPOINT"] = foundation_endpoint
        os.environ["FOUNDATION_KEY"] = foundation_key
        print("SUCCESS: Using Key Vault credentials for Foundry")
    else:
        print("WARNING: Key Vault credentials not available, using local env file")
        
except Exception as e:
    print(f"WARNING: Key Vault not available ({e}), using local env file")

# Add shared directory to path
sys.path.append('../../shared')
from evidentfit_shared.search_client import search_docs

def test_search_queries():
    """Test different search queries to understand the index structure"""
    
    print("=== Testing Search Queries ===")
    
    # Test 1: Search for any documents
    print("\n1. Searching for any documents:")
    results = search_docs("*", top=5)
    docs = results.get('value', [])
    print(f"   Found {len(docs)} total documents")
    
    if docs:
        print("   Sample document structure:")
        sample_doc = docs[0]
        for key, value in sample_doc.items():
            if key in ['supplements', 'outcomes', 'title', 'content']:
                print(f"     {key}: {str(value)[:100]}...")
    
    # Test 2: Search for creatine specifically
    print("\n2. Searching for 'creatine' in supplements field:")
    results = search_docs("supplements:creatine", top=5)
    docs = results.get('value', [])
    print(f"   Found {len(docs)} documents with supplements:creatine")
    
    # Test 3: Search for creatine in content
    print("\n3. Searching for 'creatine' in content:")
    results = search_docs("content:creatine", top=5)
    docs = results.get('value', [])
    print(f"   Found {len(docs)} documents with content:creatine")
    
    # Test 4: Search for creatine in title
    print("\n4. Searching for 'creatine' in title:")
    results = search_docs("title:creatine", top=5)
    docs = results.get('value', [])
    print(f"   Found {len(docs)} documents with title:creatine")
    
    # Test 5: Search for creatine anywhere
    print("\n5. Searching for 'creatine' anywhere:")
    results = search_docs("creatine", top=5)
    docs = results.get('value', [])
    print(f"   Found {len(docs)} documents containing 'creatine'")
    
    if docs:
        print("   Sample creatine document:")
        sample_doc = docs[0]
        print(f"     Title: {sample_doc.get('title', 'N/A')}")
        print(f"     Supplements: {sample_doc.get('supplements', 'N/A')}")
        print(f"     Content preview: {str(sample_doc.get('content', ''))[:200]}...")

if __name__ == "__main__":
    test_search_queries()
