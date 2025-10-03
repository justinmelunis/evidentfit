#!/usr/bin/env python3
"""
Count actual documents in Azure AI Search
"""
import os
import sys
sys.path.append('../../shared')

from evidentfit_shared.search_client import search_docs

def count_docs():
    """Count actual documents in the index"""
    try:
        # Get all documents
        result = search_docs('*', top=20000)
        actual_count = len(result.get('value', []))
        print(f'Actual documents in index: {actual_count}')
        
        # Estimate storage
        estimated_mb = (actual_count * 3) / 1024
        print(f'Estimated storage: ~{estimated_mb:.1f} MB')
        
        return actual_count
        
    except Exception as e:
        print(f"Error: {e}")
        return 0

if __name__ == "__main__":
    count_docs()
