import os, json, uuid, time
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from keyvault_client import get_secret
from clients.foundry_chat import chat as foundry_chat
from clients.search_read import search_docs
# Load environment variables
from dotenv import load_dotenv
load_dotenv('azure-openai.env')
load_dotenv()

# Removed Azure OpenAI client - using direct HTTP calls to AI Foundry

# ---- Pydantic models ----
class Message(BaseModel):
    role: str
    content: str

class Profile(BaseModel):
    goal: str
    weight_kg: float
    caffeine_sensitive: bool
    meds: List[str]

class StreamRequest(BaseModel):
    thread_id: str
    messages: List[Message]
    profile: Profile

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
    
    # Add API version parameter
    API_VERSION = os.getenv("FOUNDATION_API_VERSION", "2024-05-01-preview")
    url = f"{FOUNDATION_ENDPOINT.rstrip('/')}/models/chat/completions?api-version={API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": FOUNDATION_KEY.strip()
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
    
    # Add API version parameter for embeddings
    API_VERSION = os.getenv("FOUNDATION_API_VERSION", "2024-05-01-preview")
    url = f"{FOUNDATION_ENDPOINT.rstrip('/')}/models/embeddings?api-version={API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": FOUNDATION_KEY.strip()
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
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002")
ALLOWED_ORIGINS = CORS_ALLOW_ORIGINS.split(",") if CORS_ALLOW_ORIGINS else []

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

def mini_search(query: str, k: int = 8) -> List[Dict]:
    """Fallback search using sample docs when Azure AI Search is not available"""
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
    """Compose answer using Foundry chat with tight prompt that only cites retrieved IDs"""
    # Build citations from hits
    citation_lines = []
    for h in hits:
        title = h.get('title', 'Unknown')
        url = h.get('url_pub', h.get('url', ''))
        doi = h.get('doi', '')
        pmid = h.get('pmid', '')
        
        # Build citation with available identifiers
        citation_parts = [title]
        if doi:
            citation_parts.append(f"DOI: {doi}")
        if pmid:
            citation_parts.append(f"PMID: {pmid}")
        if url:
            citation_parts.append(f"URL: {url}")
        
        citation_lines.append(" - ".join(citation_parts))
    
    citations_text = "\n".join(citation_lines)
    
    sys = (
        "You are EvidentFit, an evidence-focused supplement assistant for strength athletes. "
        "Be concise, practical, and cite ONLY the provided sources. "
        "Do not invent sources or citations. Keep response under 500 tokens. "
        "Include a disclaimer at the end."
    )
    user = (
        f"User question: {prompt}\n\n"
        f"Retrieved sources (cite only these):\n{citations_text}\n\n"
        "Write an evidence-based answer that references these sources explicitly. "
        "End with 'Educational only; not medical advice.'"
    )
    
    try:
        out = foundry_chat(
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": user}],
            max_tokens=500, temperature=0.2
        )
        # Ensure disclaimer is present
        if "not medical advice" not in out.lower():
            out += "\n\n_Educational only; not medical advice._"
        return out
    except Exception as e:
        print(f"Foundry chat failed: {e}")
        return _get_fallback_answer(prompt, hits)

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
async def stream(request: StreamRequest, _=Depends(guard)):
    """SSE endpoint that emits search results then final answer"""
    thread_id = request.thread_id
    msgs = request.messages
    profile = request.profile
    
    # Get user message
    user_msg = next((m.content for m in reversed(msgs) if m.role == "user"), "")

    # Search for relevant documents
    try:
        hits = search_docs(query=user_msg, top=8)
    except Exception as e:
        print(f"Search failed, using fallback: {e}")
        hits = mini_search(user_msg, k=8)
    
    # Compose answer using Foundry chat
    answer = compose_with_llm(user_msg, hits)

    async def gen():
        # Emit search stage with hits
        search_event = {
            "stage": "search",
            "hits": [
                {
                    "title": h.get("title", ""),
                    "url_pub": h.get("url_pub", ""),
                    "study_type": h.get("study_type", ""),
                    "doi": h.get("doi", ""),
                    "pmid": h.get("pmid", "")
                }
                for h in hits
            ]
        }
        yield f"data: {json.dumps(search_event)}\n\n"
        
        # Emit final stage with answer
        final_event = {
            "stage": "final",
            "answer": answer
        }
        yield f"data: {json.dumps(final_event)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host=HOST, port=PORT)
