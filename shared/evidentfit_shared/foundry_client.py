import os, httpx

FOUNDATION_ENDPOINT = os.getenv("FOUNDATION_ENDPOINT", "").rstrip("/")
FOUNDATION_KEY = os.getenv("FOUNDATION_KEY")
API_VERSION = os.getenv("FOUNDATION_API_VERSION", "2024-05-01-preview")
EMBED_MODEL = os.getenv("FOUNDATION_EMBED_MODEL", "text-embedding-3-small")

def embed_texts(texts: list[str]) -> list[list[float]]:
    if not FOUNDATION_ENDPOINT or not FOUNDATION_KEY:
        raise RuntimeError("Foundry not configured")
    url = f"{FOUNDATION_ENDPOINT}/embeddings?api-version={API_VERSION}"
    headers = {"Content-Type": "application/json", "api-key": FOUNDATION_KEY}
    payload = {"model": EMBED_MODEL, "input": texts}
    with httpx.Client(timeout=60) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        if "data" in data and data["data"] and "embedding" in data["data"][0]:
            return [d["embedding"] for d in data["data"]]
        return [c["embedding"] for c in data["choices"]]

def chat(messages: list[dict], model: str = None, max_tokens: int = 500, temperature: float = 0.2) -> str:
    """Chat completion using Azure AI Foundry Project endpoint"""
    if not FOUNDATION_ENDPOINT or not FOUNDATION_KEY:
        raise RuntimeError("Foundry not configured")
    
    if model is None:
        model = os.getenv("FOUNDATION_CHAT_MODEL", "gpt-4o-mini")
    
    url = f"{FOUNDATION_ENDPOINT}/models/chat/completions?api-version={API_VERSION}"
    headers = {"Content-Type": "application/json", "api-key": FOUNDATION_KEY}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    
    with httpx.Client(timeout=60) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
