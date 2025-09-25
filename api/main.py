import os, json, orjson, uuid, time
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from inference_client import foundry_chat
from keyvault_client import get_secret
# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    # Try to load azure-openai.env first, then .env
    load_dotenv('azure-openai.env')
    load_dotenv()
    print("Environment variables loaded successfully")
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")
    print("Continuing with system environment variables...")

# Import Azure OpenAI (optional)
try:
    from openai import AzureOpenAI
    AZURE_OPENAI_AVAILABLE = True
except ImportError:
    print("Warning: Azure OpenAI not available. Using fallback responses.")
    AzureOpenAI = None
    AZURE_OPENAI_AVAILABLE = False

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
AZURE_INFERENCE_ENDPOINT = get_secret("azure-inference-endpoint", os.getenv("AZURE_INFERENCE_ENDPOINT"), force_refresh=True)
AZURE_INFERENCE_KEY = get_secret("FoundryApiKey", os.getenv("AZURE_INFERENCE_KEY"), force_refresh=True)
AZURE_INFERENCE_CHAT_MODEL = get_secret("azure-inference-chat-model", os.getenv("AZURE_INFERENCE_CHAT_MODEL", "gpt-4o-mini"), force_refresh=True)
AZURE_INFERENCE_EMBED_MODEL = get_secret("azure-inference-embed-model", os.getenv("AZURE_INFERENCE_EMBED_MODEL", "text-embedding-3-small"), force_refresh=True)

# Initialize Azure AI Foundry client
azure_openai_client = None
if AZURE_OPENAI_AVAILABLE and AZURE_INFERENCE_ENDPOINT and AZURE_INFERENCE_KEY:
    try:
        azure_openai_client = AzureOpenAI(
            azure_endpoint=AZURE_INFERENCE_ENDPOINT,
            api_key=AZURE_INFERENCE_KEY,
            api_version="2024-02-15-preview"
        )
        print("Azure AI Foundry client initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize Azure AI Foundry client: {e}")
        azure_openai_client = None
else:
    print("Azure AI Foundry not configured - using fallback responses")

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
        DOCS = orjson.loads(f.read())

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

@api.get("/test")
def test_stream():
    """Test endpoint to demonstrate the stream functionality"""
    test_payload = {
        "thread_id": "test-123",
        "messages": [
            {"role": "user", "content": "tell me about caffeine"}
        ]
    }
    
    # Simulate the stream logic
    user_msg = "tell me about caffeine"
    hits = mini_search(user_msg, k=3)
    answer = compose_with_llm(user_msg, hits)
    
    return {
        "message": "This is what the /stream endpoint would return",
        "test_payload": test_payload,
        "search_results": hits,
        "answer": answer
    }

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
