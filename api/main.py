import os, json, orjson, uuid, time
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# ---- Pydantic models ----
class Message(BaseModel):
    role: str
    content: str

class StreamRequest(BaseModel):
    thread_id: str = None
    messages: List[Message]

# ---- auth (private preview) ----
security = HTTPBasic()
DEMO_USER = os.getenv("DEMO_USER", "demo")
DEMO_PW = os.getenv("DEMO_PW", "demo123")

def guard(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != DEMO_USER or creds.password != DEMO_PW:
        raise HTTPException(401, "Unauthorized")

api = FastAPI(title="EvidentFit API", version="0.0.1")

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

def compose_answer(prompt: str, hits: List[Dict]) -> str:
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
    answer = compose_answer(user_msg, hits)
    
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
async def stream(request: StreamRequest, _=Depends(guard)):
    thread_id = request.thread_id or str(uuid.uuid4())
    msgs = request.messages
    user_msg = next((m.content for m in reversed(msgs) if m.role == "user"), "")
    hits = mini_search(user_msg, k=3)
    answer = compose_answer(user_msg, hits)

    async def gen():
        # stream in two chunks to exercise the SSE client
        frame1 = {"thread_id": thread_id, "stage": "search", "hits": hits}
        yield f"data: {json.dumps(frame1)}\n\n"
        time.sleep(0.15)
        frame2 = {"thread_id": thread_id, "stage": "final", "answer": answer}
        yield f"data: {json.dumps(frame2)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
