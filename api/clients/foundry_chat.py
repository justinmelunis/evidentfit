"""
Azure AI Foundry chat completions client
Uses Project endpoint with api-key header and api-version parameter
"""
import os
import httpx
from typing import List, Dict, Any


def chat(
    messages: List[Dict[str, str]], 
    model: str = None, 
    max_tokens: int = 500, 
    temperature: float = 0.2
) -> str:
    """
    Chat completion using Azure AI Foundry Project endpoint
    
    Args:
        messages: List of {"role": "system|user|assistant", "content": "..."}
        model: Model name (defaults to FOUNDATION_CHAT_MODEL env var)
        max_tokens: Maximum tokens to generate (default 500)
        temperature: Sampling temperature (default 0.2)
    
    Returns:
        Generated content string
        
    Raises:
        Exception: For non-200 responses or missing configuration
    """
    # Get configuration from environment
    foundation_endpoint = os.getenv("FOUNDATION_ENDPOINT")
    foundation_key = os.getenv("FOUNDATION_KEY")
    foundation_api_version = os.getenv("FOUNDATION_API_VERSION", "2024-05-01-preview")
    
    if not foundation_endpoint or not foundation_key:
        raise Exception("Azure AI Foundry not configured: missing FOUNDATION_ENDPOINT or FOUNDATION_KEY")
    
    if model is None:
        model = os.getenv("FOUNDATION_CHAT_MODEL", "gpt-4o-mini")
    
    # Build Project endpoint URL
    url = f"{foundation_endpoint.rstrip('/')}/models/chat/completions?api-version={foundation_api_version}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": foundation_key.strip()
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        # Log concise error details
        print(f"Foundry chat error: {e.response.status_code} - {e.response.text[:200]}")
        raise Exception(f"Foundry chat failed: {e.response.status_code}")
    except Exception as e:
        print(f"Foundry chat error: {str(e)[:200]}")
        raise
