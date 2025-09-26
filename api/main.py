import os, json, uuid, time
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# Removed inference_client import - using Azure OpenAI client directly
from keyvault_client import get_secret
# Load environment variables
from dotenv import load_dotenv
load_dotenv('azure-openai.env')
load_dotenv()

# Removed Azure OpenAI client - using direct HTTP calls to AI Foundry

# ---- Pydantic models ----
class Message(BaseModel):
    role: str
    content: str

class StreamRequest(BaseModel):
    thread_id: str = None
    messages: List[Message]

# ---- auth (private preview) ----
security = HTTPBasic()
DEMO_USER = get_secret("demo-user", os.getenv("DEMO_USER", "demo"))
DEMO_PW = get_secret("demo-password", os.getenv("DEMO_PW", "demo123"))

# ---- Azure deployment configuration ----
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ---- Azure AI Foundry configuration (with Key Vault fallback) ----
# Try to get secrets from Key Vault first, fallback to environment variables
# Use force_refresh=True to bypass any caching issues
FOUNDATION_ENDPOINT = get_secret("foundation-endpoint", os.getenv("FOUNDATION_ENDPOINT"), force_refresh=True)
FOUNDATION_KEY = get_secret("foundation-key", os.getenv("FOUNDATION_KEY"), force_refresh=True)
FOUNDATION_CHAT_MODEL = get_secret("foundation-chat-model", os.getenv("FOUNDATION_CHAT_MODEL", "gpt-4o-mini"), force_refresh=True)
FOUNDATION_EMBED_MODEL = get_secret("foundation-embed-model", os.getenv("FOUNDATION_EMBED_MODEL", "text-embedding-3-small"), force_refresh=True)

# ---- Azure AI Search configuration (with Key Vault fallback) ----
SEARCH_ENDPOINT = get_secret("search-endpoint", os.getenv("SEARCH_ENDPOINT"), force_refresh=True)
SEARCH_QUERY_KEY = get_secret("search-query-key", os.getenv("SEARCH_QUERY_KEY"), force_refresh=True)
SEARCH_INDEX = get_secret("search-index", os.getenv("SEARCH_INDEX", "evidentfit-index"), force_refresh=True)
INDEX_VERSION = get_secret("index-version", os.getenv("INDEX_VERSION", "v1-2025-09-25"), force_refresh=True)

# Azure AI Foundry configuration check
if FOUNDATION_ENDPOINT and FOUNDATION_KEY:
    print("Azure AI Foundry configured successfully")
else:
    print("Azure AI Foundry not configured - using fallback responses")

# Helper functions to replace inference_client
def foundry_chat(messages, max_tokens=500, temperature=0.2):
    """
    Chat completion using Azure AI Foundry
    messages: list of {"role":"system"|"user"|"assistant", "content": "..."}
    returns: string content
    """
    import httpx
    
    if not FOUNDATION_ENDPOINT or not FOUNDATION_KEY:
        raise Exception("Azure AI Foundry not configured")
    
    url = f"{FOUNDATION_ENDPOINT}/chat/completions"
    headers = {
        "api-key": FOUNDATION_KEY,
        "content-type": "application/json"
    }
    payload = {
        "model": FOUNDATION_CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    r = httpx.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def foundry_embed(texts):
    """
    Generate embeddings using Azure AI Foundry
    texts: list[str]
    returns: list[list[float]] (embeddings)
    """
    import httpx
    
    if not FOUNDATION_ENDPOINT or not FOUNDATION_KEY:
        raise Exception("Azure AI Foundry not configured")
    
    url = f"{FOUNDATION_ENDPOINT}/embeddings"
    headers = {
        "api-key": FOUNDATION_KEY,
        "content-type": "application/json"
    }
    payload = {
        "model": FOUNDATION_EMBED_MODEL,
        "input": texts
    }
    
    r = httpx.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return [d["embedding"] for d in data["data"]]

def guard(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != DEMO_USER or creds.password != DEMO_PW:
        raise HTTPException(401, "Unauthorized")

api = FastAPI(title="EvidentFit API", version="0.0.1")

# CORS configuration for Azure deployment
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002").split(",")

api.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- tiny in-memory "index" ----
DOCS: List[Dict] = []
DOCS_PATH = os.path.join(os.path.dirname(__file__), "sample_docs.json")
if os.path.exists(DOCS_PATH):
    with open(DOCS_PATH, "rb") as f:
        DOCS = json.loads(f.read())

def mini_search(query: str, k: int = 3) -> List[Dict]:
    q = query.lower()
    scored = []
    for d in DOCS:
        score = sum(q.count(kw.lower()) for kw in d.get("keywords", []))
        # fallback: substring in title/summary
        score += (d["title"].lower().count(q) + d["summary"].lower().count(q))
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:k]] or DOCS[:k]

def compose_with_llm(prompt: str, hits: list[dict]) -> str:
    citation_lines = "\n".join([f"- {h['title']} — {h['url']}" for h in hits])
    sys = (
        "You are EvidentFit, an evidence-focused supplement assistant for strength athletes. "
        "Be concise, practical, and cite the provided sources at the end. "
        "Do not invent sources. Include a short disclaimer."
    )
    user = (
        f"User question: {prompt}\n\n"
        f"Top sources:\n{citation_lines}\n\n"
        "Write an answer that references these sources explicitly."
    )
    out = foundry_chat(
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": user}],
        max_tokens=450, temperature=0.2
    )
    # Ensure citations block appears even if the model forgets
    if "Citations" not in out:
        out += "\n\n**Citations**\n" + citation_lines
    if "not medical advice" not in out.lower():
        out += "\n\n_Educational only; not medical advice._"
    return out

def _get_fallback_answer(prompt: str, hits: List[Dict]) -> str:
    """Fallback response when Azure OpenAI is not available"""
    lines = []
    lines.append(f"**Answer (draft)**")
    lines.append(f"- You asked: _{prompt}_")
    lines.append("")
    if "caffeine" in prompt.lower() and any("mg/kg" in h["summary"].lower() for h in hits):
        lines.append("**Caffeine (general guidance)**: about 3–6 mg/kg pre-workout, but adjust for sensitivity.")
    if "creatine" in prompt.lower():
        lines.append("**Creatine monohydrate**: 3–5 g/day; optional loading 20 g/day × 5–7 days.")
    if "beta" in prompt.lower():
        lines.append("**Beta-alanine**: ~3.2–6.4 g/day split to reduce paresthesia.")
    lines.append("")
    lines.append("**Citations**:")
    for h in hits:
        lines.append(f"- {h['title']} — {h['url']}")
    lines.append("")
    lines.append("_Educational only; not medical advice._")
    return "\n".join(lines)

@api.get("/")
def root():
    return {
        "message": "EvidentFit API is running!",
        "version": "0.0.1",
        "endpoints": {
            "health": "/healthz",
            "stream": "/stream (POST, requires auth)",
            "docs": "/docs"
        },
        "auth": {
            "username": "demo",
            "password": "demo123"
        }
    }

# Removed /test endpoint - not needed for production

@api.get("/healthz")
def healthz():
    return {"ok": True, "docs_loaded": len(DOCS)}

@api.post("/stream")
async def stream(request: Request, _=Depends(guard)):
    payload = await request.json()
    thread_id = payload.get("thread_id") or str(uuid.uuid4())
    msgs = payload.get("messages", [])
    user_msg = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")

    hits = mini_search(user_msg, k=3)
    answer = compose_with_llm(user_msg, hits)  # <-- now using Foundry chat

    async def gen():
        yield f"data: {json.dumps({'thread_id': thread_id, 'stage': 'search', 'hits': hits})}\n\n"
        yield f"data: {json.dumps({'thread_id': thread_id, 'stage': 'final', 'answer': answer})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)
