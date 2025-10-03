#!/usr/bin/env python3
"""
Force clear Azure AI Search index by deleting and recreating it
"""
import os
import httpx
import sys
sys.path.append('../../shared')

def force_clear_index():
    """Force clear index by deleting and recreating it"""
    try:
        SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
        SEARCH_ADMIN_KEY = os.getenv("SEARCH_ADMIN_KEY") 
        SEARCH_INDEX = os.getenv("SEARCH_INDEX", "evidentfit-index")
        
        if not all([SEARCH_ENDPOINT, SEARCH_ADMIN_KEY]):
            print("Missing required environment variables")
            return False
            
        headers = {"api-key": SEARCH_ADMIN_KEY, "Content-Type": "application/json"}
        
        # Delete the index
        print(f"Deleting index: {SEARCH_INDEX}")
        delete_url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}?api-version=2023-11-01"
        
        with httpx.Client(timeout=60, headers=headers) as c:
            r = c.delete(delete_url)
            print(f"Delete response: {r.status_code}")
            if r.status_code not in [204, 404]:
                print(f"Delete error: {r.text}")
                return False
                
        # Recreate the index
        print(f"Recreating index: {SEARCH_INDEX}")
        from evidentfit_shared.search_client import ensure_index
        ensure_index()
        
        print("Index force cleared and recreated successfully")
        return True
        
    except Exception as e:
        print(f"Error force clearing index: {e}")
        return False

if __name__ == "__main__":
    success = force_clear_index()
    sys.exit(0 if success else 1)
