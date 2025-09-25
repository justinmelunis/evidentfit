import os, json, orjson, uuid, time
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
DEMO_USER = os.getenv("DEMO_USER", "demo")
DEMO_PW = os.getenv("DEMO_PW", "demo123")

# ---- Azure deployment configuration ----
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ---- Azure OpenAI configuration ----
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")

# Initialize Azure OpenAI client
azure_openai_client = None
if AZURE_OPENAI_AVAILABLE and AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
    try:
        azure_openai_client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )
        print("Azure OpenAI client initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize Azure OpenAI client: {e}")
        azure_openai_client = None
else:
    print("Azure OpenAI not configured - using fallback responses")

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

async def compose_answer(prompt: str, hits: List[Dict]) -> str:
    """
    Generate an evidence-based answer using Azure OpenAI with retrieved research papers
    """
    print(f"DEBUG: azure_openai_client is {azure_openai_client}")
    print(f"DEBUG: Using fallback mode")
    
    if not azure_openai_client:
        # Fallback to stubbed response if Azure OpenAI is not configured
        print("DEBUG: Using fallback response")
        return _get_fallback_answer(prompt, hits)
    
    # Prepare context from retrieved papers
    context_papers = []
    for hit in hits:
        context_papers.append(f"**{hit['title']}**\nSummary: {hit['summary']}\nURL: {hit['url']}")
    
    context = "\n\n".join(context_papers)
    
    # Create the system prompt for evidence-based fitness guidance
    system_prompt = """You are an evidence-based fitness and supplement expert. You provide accurate, research-backed guidance on fitness supplements, nutrition, and training.

Guidelines:
- Base your answers on the provided research papers
- Be specific about dosages, timing, and protocols
- Always include proper citations
- Emphasize that this is educational, not medical advice
- Use a professional but accessible tone
- Structure your response clearly with headings and bullet points"""

    user_prompt = f"""Based on the following research papers, provide evidence-based guidance for this question: "{prompt}"

Research Papers:
{context}

Please provide a comprehensive, evidence-based answer that:
1. Directly addresses the user's question
2. References specific findings from the research papers
3. Includes practical recommendations with dosages
4. Lists all citations properly
5. Emphasizes this is educational, not medical advice"""

    try:
        response = azure_openai_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent, factual responses
            max_tokens=1000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Azure OpenAI error: {e}")
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
    answer = await compose_answer(user_msg, hits)

    async def gen():
        # stream in two chunks to exercise the SSE client
        frame1 = {"thread_id": thread_id, "stage": "search", "hits": hits}
        yield f"data: {json.dumps(frame1)}\n\n"
        time.sleep(0.15)
        frame2 = {"thread_id": thread_id, "stage": "final", "answer": answer}
        yield f"data: {json.dumps(frame2)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
