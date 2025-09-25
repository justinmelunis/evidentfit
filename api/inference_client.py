import os, httpx
from dotenv import load_dotenv

# Load environment variables from azure-openai.env file
load_dotenv('azure-openai.env')
load_dotenv()

F_ENDPOINT = os.getenv("AZURE_INFERENCE_ENDPOINT", "").rstrip("/")
F_KEY = os.getenv("AZURE_INFERENCE_KEY", "")
CHAT_MODEL = os.getenv("AZURE_INFERENCE_CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("AZURE_INFERENCE_EMBED_MODEL", "text-embedding-3-small")

HEADERS = {
    "api-key": F_KEY,
    "content-type": "application/json"
}

def foundry_chat(messages, max_tokens=500, temperature=0.2):
    """
    messages: list of {"role":"system"|"user"|"assistant", "content": "..."}
    returns: string content
    """
    url = f"{F_ENDPOINT}/chat/completions"
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    r = httpx.post(url, json=payload, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def foundry_embed(texts):
    """
    texts: list[str]
    returns: list[list[float]] (embeddings)
    """
    url = f"{F_ENDPOINT}/embeddings"
    payload = {
        "model": EMBED_MODEL,
        "input": texts
    }
    r = httpx.post(url, json=payload, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    # OpenAI-style response: {"data":[{"embedding":[...], "index":0}, ...]}
    return [d["embedding"] for d in data["data"]]
