#!/usr/bin/env python3
"""
Delete the entire Azure AI Search index.
"""

import os
import httpx

SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "").rstrip("/")
SEARCH_INDEX = os.getenv("SEARCH_INDEX", "evidentfit-index")
ADMIN_KEY = os.getenv("SEARCH_ADMIN_KEY")
API_VERSION = "2023-11-01"

if not SEARCH_ENDPOINT:
    raise RuntimeError("SEARCH_ENDPOINT environment variable is required")
if not ADMIN_KEY:
    raise RuntimeError("SEARCH_ADMIN_KEY environment variable is required")

def delete_index():
    """Delete the entire index"""
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}?api-version={API_VERSION}"
    headers = {"api-key": ADMIN_KEY}
    
    with httpx.Client(timeout=60, headers=headers) as c:
        r = c.delete(url)
        if r.status_code == 204:
            print(f"Index '{SEARCH_INDEX}' deleted successfully")
        elif r.status_code == 404:
            print(f"Index '{SEARCH_INDEX}' not found (already deleted)")
        else:
            print(f"Error deleting index: {r.status_code} - {r.text}")
            r.raise_for_status()

if __name__ == "__main__":
    delete_index()
