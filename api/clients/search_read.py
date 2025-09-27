"""
Azure AI Search read client
Uses REST API 2023-11-01 with hybrid query
"""
import os
import httpx
from typing import List, Dict, Any, Optional


def search_docs(
    query: str, 
    filters: Optional[str] = None, 
    select: Optional[List[str]] = None,
    top: int = 8
) -> List[Dict[str, Any]]:
    """
    Search documents using Azure AI Search with hybrid query
    
    Args:
        query: Search query string
        filters: OData filter expression (optional)
        select: List of fields to return (optional)
        top: Maximum number of results (default 8)
    
    Returns:
        List of document dictionaries with selected fields
    """
    # Get configuration from environment
    search_endpoint = os.getenv("SEARCH_ENDPOINT")
    search_query_key = os.getenv("SEARCH_QUERY_KEY")
    search_index = os.getenv("SEARCH_INDEX", "evidentfit-index")
    
    if not search_endpoint or not search_query_key:
        raise Exception("Azure AI Search not configured: missing SEARCH_ENDPOINT or SEARCH_QUERY_KEY")
    
    # Default select fields for Papers index
    if select is None:
        select = ["title", "url_pub", "study_type", "doi", "pmid"]
    
    # Build search URL
    url = f"{search_endpoint.rstrip('/')}/indexes/{search_index}/docs/search"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": search_query_key.strip()
    }
    
    # Build hybrid query (BM25 text search on title, summary, content)
    search_payload = {
        "search": query,
        "queryType": "simple",  # Use simple query for BM25
        "searchFields": ["title", "summary", "content"],
        "select": select,
        "top": top
    }
    
    if filters:
        search_payload["filter"] = filters
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=search_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("value", [])
    except httpx.HTTPStatusError as e:
        print(f"Search error: {e.response.status_code} - {e.response.text[:200]}")
        raise Exception(f"Search failed: {e.response.status_code}")
    except Exception as e:
        print(f"Search error: {str(e)[:200]}")
        raise
