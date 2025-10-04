#!/usr/bin/env python3
"""
Test creatine search specifically
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

def test_creatine_search():
    """Test creatine search with the new approach"""
    
    print("=== Testing Creatine Search ===")
    
    # Search for creatine
    query = "creatine"
    search_results = search_docs(query, top=100)
    papers = search_results.get('value', [])
    
    print(f"Found {len(papers)} papers containing 'creatine'")
    
    # Filter for papers that actually have creatine in supplements field
    creatine_papers = []
    for paper in papers:
        supplements_field = (paper.get("supplements") or "").lower()
        if "creatine" in supplements_field:
            creatine_papers.append(paper)
    
    print(f"Found {len(creatine_papers)} papers with creatine in supplements field")
    
    if creatine_papers:
        print("\nSample creatine papers:")
        for i, paper in enumerate(creatine_papers[:3]):
            print(f"\n{i+1}. {paper.get('title', 'N/A')}")
            print(f"   Supplements: {paper.get('supplements', 'N/A')}")
            print(f"   Study Type: {paper.get('study_type', 'N/A')}")
            print(f"   Year: {paper.get('year', 'N/A')}")
    
    # Test goal filtering for strength
    print(f"\n=== Testing Strength Goal Filtering ===")
    strength_keywords = ["strength", "1rm", "power", "force", "muscle strength"]
    
    strength_papers = []
    for paper in creatine_papers:
        title = (paper.get("title") or "").lower()
        content = (paper.get("content") or "").lower()
        outcomes = (paper.get("outcomes") or "").lower()
        primary_goal = (paper.get("primary_goal") or "").lower()
        
        text_to_check = f"{title} {content} {outcomes} {primary_goal}"
        if any(keyword in text_to_check for keyword in strength_keywords):
            strength_papers.append(paper)
    
    print(f"Found {len(strength_papers)} creatine papers relevant to strength goals")
    
    if strength_papers:
        print("\nSample strength-relevant creatine papers:")
        for i, paper in enumerate(strength_papers[:3]):
            print(f"\n{i+1}. {paper.get('title', 'N/A')}")
            print(f"   Supplements: {paper.get('supplements', 'N/A')}")
            print(f"   Study Type: {paper.get('study_type', 'N/A')}")

if __name__ == "__main__":
    test_creatine_search()
