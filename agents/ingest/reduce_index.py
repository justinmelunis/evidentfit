#!/usr/bin/env python3
"""
Reduce index to 10,000 papers and remove unused fields.
This script will:
1. Get all documents from the index
2. Sort by enhanced_score (descending)
3. Keep only the top 10,000 papers
4. Remove the unused fields from each document
5. Update the index with the reduced dataset
"""

import os
import json
from evidentfit_shared.search_client import search_docs, upsert_docs, ensure_index

def reduce_index():
    """Reduce index to 10,000 papers and remove unused fields"""
    
    print("Fetching all documents from index...")
    
    # Get all documents (we'll need to paginate)
    all_docs = []
    skip = 0
    batch_size = 1000
    
    while True:
        print(f"  Fetching batch {skip//batch_size + 1} (skip={skip})...")
        
        # Search with pagination
        results = search_docs(
            query="*",
            top=batch_size,
            skip=skip,
            select=["*"]  # Get all fields
        )
        
        docs = results.get('value', [])
        if not docs:
            break
            
        all_docs.extend(docs)
        skip += batch_size
        
        # Safety check
        if len(all_docs) > 15000:  # Shouldn't happen, but safety first
            print(f"Warning: Found {len(all_docs)} documents, stopping at 15,000")
            break
    
    print(f"Total documents found: {len(all_docs)}")
    
    if len(all_docs) <= 10000:
        print("Index already has <=10,000 papers, no reduction needed")
        return
    
    # Sort by enhanced_score (descending) to keep the best papers
    print("Sorting papers by enhanced_score...")
    all_docs.sort(key=lambda x: x.get('enhanced_score') or 0, reverse=True)
    
    # Keep top 10,000 papers
    top_docs = all_docs[:10000]
    print(f"Keeping top {len(top_docs)} papers (removing {len(all_docs) - len(top_docs)})")
    
    # Remove unused fields from each document
    print("Removing unused fields...")
    
    fields_to_remove = [
        'hypertrophy_outcomes',
        'weight_loss_outcomes', 
        'strength_outcomes',
        'performance_outcomes',
        'sample_size_category',
        'duration_category',
        'population_category',
        'first_author',
        'author_count',
        'funding_sources',
        'mesh_terms',
        'keywords',
        'content_vector'
    ]
    
    cleaned_docs = []
    for doc in top_docs:
        # Create new document without the unused fields
        cleaned_doc = {k: v for k, v in doc.items() if k not in fields_to_remove}
        cleaned_docs.append(cleaned_doc)
    
    print(f"Cleaned {len(cleaned_docs)} documents")
    
    # Clear the entire index first
    print("Clearing index...")
    try:
        from evidentfit_shared.search_client import clear_index
        clear_index()
        print("Index cleared")
    except Exception as e:
        print(f"Could not clear index: {e}")
        print("Proceeding with upsert (will overwrite existing docs)")
    
    # Recreate index with simplified schema
    print("Recreating index with simplified schema...")
    ensure_index()
    
    # Upload the cleaned documents in batches
    print("Uploading cleaned documents...")
    batch_size = 50
    total_uploaded = 0
    
    for i in range(0, len(cleaned_docs), batch_size):
        batch = cleaned_docs[i:i+batch_size]
        try:
            upsert_docs(batch)
            total_uploaded += len(batch)
            print(f"  Uploaded {total_uploaded}/{len(cleaned_docs)} documents")
        except Exception as e:
            print(f"Error uploading batch {i//batch_size + 1}: {e}")
            break
    
    print(f"Successfully reduced index to {total_uploaded} documents")
    
    # Update watermark
    print("Updating watermark...")
    from datetime import datetime
    now_iso = datetime.now().isoformat()
    wm_doc = {
        "id": "meta:last_ingest",
        "last_ingest_iso": now_iso,
        "paper_count": total_uploaded,
        "index_version": os.getenv("INDEX_VERSION", "v1")
    }
    upsert_docs([wm_doc])
    print(f"Watermark updated to {now_iso}")

if __name__ == "__main__":
    reduce_index()
