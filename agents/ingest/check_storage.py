#!/usr/bin/env python3
"""
Check Azure AI Search storage usage
"""
import os
import sys
sys.path.append('../../shared')

from evidentfit_shared.search_client import search_docs

def check_storage():
    """Check current storage usage in Azure AI Search"""
    try:
        # Search for all documents to get count
        response = search_docs(query="*", top=1)
        
        total_docs = response.get("@odata.count", "unknown")
        if total_docs == "unknown":
            # Try to get count from value array length
            docs = response.get("value", [])
            if docs:
                # Get a larger sample to estimate
                response2 = search_docs(query="*", top=1000)
                total_docs = len(response2.get("value", []))
                print(f"Sample count: {total_docs} (from 1000 sample)")
            else:
                total_docs = 0
        print(f"Total documents in index: {total_docs}")
        
        # Estimate storage usage (rough calculation)
        if total_docs != "unknown":
            # Rough estimate: 2-5KB per document
            estimated_kb = int(total_docs) * 3  # 3KB average
            estimated_mb = estimated_kb / 1024
            print(f"Estimated storage usage: ~{estimated_mb:.1f} MB")
            
            # Azure AI Search free tier limit is 50MB
            if estimated_mb > 45:
                print("⚠️  WARNING: Approaching 50MB free tier limit!")
                print("   Consider upgrading to Basic tier ($75/month) for 2GB storage")
            elif estimated_mb > 40:
                print("⚠️  WARNING: Storage usage is high (>40MB)")
            else:
                print("✅ Storage usage is within safe limits")
        
        return total_docs
        
    except Exception as e:
        print(f"Error checking storage: {e}")
        return None

if __name__ == "__main__":
    check_storage()
