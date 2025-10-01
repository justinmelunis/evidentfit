import os, json, uuid, time
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# Use shared clients instead of local ones
try:
    from evidentfit_shared.foundry_client import embed_texts, chat as foundry_chat
    from evidentfit_shared.search_client import ensure_index, upsert_docs, get_doc, search_docs
except ImportError:
    # Fallback to local clients if shared not available
    from clients.foundry_chat import chat as foundry_chat
    from clients.search_read import search_docs

# Import stack rules and conversational builder
from stack_rules import creatine_plan_by_form, protein_gap_plan, get_evidence_grade, get_supplement_timing, get_supplement_why
try:
    from stack_builder import build_conversational_stack, get_creatine_form_comparison
    from evidentfit_shared.types import UserProfile, StackPlan
    CONVERSATIONAL_STACK_AVAILABLE = True
except ImportError:
    CONVERSATIONAL_STACK_AVAILABLE = False
    print("Warning: Conversational stack builder not available")
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
    diet: Optional[str] = None
    training_freq: Optional[str] = None
    diet_protein_g_per_day: Optional[float] = None
    diet_protein_g_per_kg: Optional[float] = None
    creatine_form: Optional[str] = None

class StackRequest(BaseModel):
    profile: Profile
    tier: Optional[str] = None

class StreamRequest(BaseModel):
    thread_id: str
    messages: List[Message]
    profile: Profile

class ConversationalStackRequest(BaseModel):
    """Request for conversational stack endpoint"""
    thread_id: str
    messages: List[Message]
    profile: Profile

# ---- auth (private preview) ----
security = HTTPBasic()
DEMO_USER = os.getenv("DEMO_USER", "demo")
DEMO_PW = os.getenv("DEMO_PW", "demo123")

# ---- Azure deployment configuration ----
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ---- Azure AI Foundry configuration ----
FOUNDATION_ENDPOINT = os.getenv("FOUNDATION_ENDPOINT")
FOUNDATION_KEY = os.getenv("FOUNDATION_KEY")
FOUNDATION_CHAT_MODEL = os.getenv("FOUNDATION_CHAT_MODEL", "gpt-4o-mini")
FOUNDATION_EMBED_MODEL = os.getenv("FOUNDATION_EMBED_MODEL", "text-embedding-3-small")

# ---- Azure AI Search configuration ----
SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
SEARCH_QUERY_KEY = os.getenv("SEARCH_QUERY_KEY")
SEARCH_INDEX = os.getenv("SEARCH_INDEX", "evidentfit-index")
SEARCH_SUMMARIES_INDEX = os.getenv("SEARCH_SUMMARIES_INDEX", "evidentfit-summaries")
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1-2025-09-25")

# Azure AI Foundry configuration check
if FOUNDATION_ENDPOINT and FOUNDATION_KEY:
    print("Azure AI Foundry configured successfully")
else:
    print("Azure AI Foundry not configured - using fallback responses")

# Removed duplicate foundry_chat function - using clients/foundry_chat.py

# Removed foundry_embed function - not used in current implementation

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
    """Health check endpoint that reports actual index doc count"""
    try:
        # Query the actual index to get document count
        search_response = search_docs(query="*", top=1)
        # Azure AI Search returns the count in @odata.count if requested
        # For now, we'll just confirm we can connect
        index_available = True
        fallback_count = len(DOCS)
    except Exception as e:
        print(f"Index health check failed: {e}")
        index_available = False
        fallback_count = len(DOCS)
    
    return {
        "ok": True, 
        "docs_loaded": fallback_count,
        "index_available": index_available,
        "using_fallback": not index_available
    }

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
        search_response = search_docs(query=user_msg, top=8)
        hits = search_response.get('value', [])
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

@api.get("/summaries/{supplement}")
def get_summary(supplement: str):
    """Get supplement summary from Summaries index"""
    try:
        # Try to get summary from shared search client
        if 'get_doc' in globals():
            summary_doc = get_doc(f"summary:{supplement}")
            if summary_doc:
                return {
                    "supplement": supplement,
                    "evidence_grade": summary_doc.get("evidence_grade", "D"),
                    "updated_at": summary_doc.get("updated_at", ""),
                    "overview_md": summary_doc.get("overview_md", ""),
                    "last12_md": summary_doc.get("last12_md", ""),
                    "key_papers": json.loads(summary_doc.get("key_papers_json", "[]")),
                    "recent_papers": json.loads(summary_doc.get("recent_papers_json", "[]")),
                    "index_version": summary_doc.get("index_version", INDEX_VERSION)
                }
    except Exception as e:
        print(f"Error fetching summary: {e}")
    
    # Fallback response if summary not found
    raise HTTPException(status_code=404, detail=f"Summary not found for supplement: {supplement}")

@api.post("/stack")
def build_stack(request: StackRequest):
    """Build deterministic supplement stack based on profile"""
    profile = request.profile
    tier = request.tier or "standard"
    
    # Build bucket key
    weight_bin = round(profile.weight_kg / 5) * 5
    stim = "sens" if profile.caffeine_sensitive else "ok"
    meds_class = "none"  # Simplified for now
    diet = profile.diet or "any"
    training_freq = profile.training_freq or "med"
    
    bucket_key = f"{INDEX_VERSION}:{profile.goal}:{weight_bin}:{stim}:{meds_class}:{diet}:{training_freq}"
    
    # Build stack tiers
    core = []
    optional = []
    conditional = []
    experimental = []
    
    # Core supplements based on goal
    if profile.goal in ["strength", "hypertrophy"]:
        # Creatine
        creatine_plan = creatine_plan_by_form(
            profile.weight_kg, 
            profile.creatine_form, 
            include_loading=True
        )
        core.append(creatine_plan)
        
        # Protein gap
        protein_plan = protein_gap_plan(
            profile.goal,
            profile.weight_kg,
            profile.diet_protein_g_per_day,
            profile.diet_protein_g_per_kg
        )
        if protein_plan:
            core.append(protein_plan)
        
        # Caffeine (if not sensitive)
        if not profile.caffeine_sensitive:
            core.append({
                "supplement": "caffeine",
                "doses": [{"value": 3, "unit": "mg/kg", "days": None}],
                "timing": "Pre-workout",
                "evidence": "A",
                "why": "Improves focus, energy, and performance",
                "notes": ["Avoid late in day"]
            })
    
    elif profile.goal == "endurance":
        # Beta-alanine for endurance
        optional.append({
            "supplement": "beta-alanine",
            "doses": [{"value": 3.2, "unit": "g", "days": None, "split": "2x daily"}],
            "timing": "Split throughout day",
            "evidence": "B",
            "why": "Buffers muscle acidity, delays fatigue",
            "notes": ["May cause paresthesia (tingling)"]
        })
    
    # Build response
    response = {
        "bucket_key": bucket_key,
        "profile_sig": profile.dict(),
        "tiers": {
            "core": core,
            "optional": optional,
            "conditional": conditional,
            "experimental": experimental
        },
        "exclusions": [],
        "safety": [],
        "index_version": INDEX_VERSION,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    return response

@api.get("/stack/bucket/{bucket_key}")
def get_bucket(bucket_key: str):
    """Get banked stack recipe by bucket key"""
    try:
        if 'get_doc' in globals():
            doc = get_doc(bucket_key)
            if doc:
                return json.loads(doc.get("recipe", "{}"))
    except Exception as e:
        print(f"Error fetching bucket: {e}")
    
    raise HTTPException(status_code=404, detail=f"Bucket not found: {bucket_key}")

@api.get("/stack/buckets")
def list_buckets():
    """List known buckets (admin endpoint)"""
    # This would require a more complex search query
    # For now, return empty list
    return {"buckets": []}

@api.post("/stack/conversational")
async def stack_conversational(request: ConversationalStackRequest, _=Depends(guard)):
    """
    Build a personalized supplement stack through conversational interaction.
    
    Combines user profile with chat context to:
    - Answer specific questions about supplements
    - Build evidence-based stack recommendations
    - Explain dosing and form alternatives
    - Apply safety guardrails
    """
    if not CONVERSATIONAL_STACK_AVAILABLE:
        raise HTTPException(status_code=501, detail="Conversational stack not available")
    
    # Extract user message for context
    user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    
    # Convert Profile to UserProfile
    profile_dict = request.profile.dict()
    try:
        user_profile = UserProfile(**profile_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {str(e)}")
    
    # Build search query from profile goal + user message
    search_query = f"{user_profile.goal} {user_msg}"
    
    # Search for relevant papers
    try:
        search_response = search_docs(query=search_query, top=15)
        docs = search_response.get('value', [])
        print(f"Found {len(docs)} papers for query: {search_query}")
    except Exception as e:
        print(f"Search failed: {e}")
        docs = []
    
    # Build stack plan with conversation context
    try:
        stack_plan = build_conversational_stack(
            profile=user_profile,
            retrieved_docs=docs,
            conversation_context=user_msg
        )
    except Exception as e:
        print(f"Stack building failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build stack: {str(e)}")
    
    # Compose conversational explanation using LLM
    explanation = _compose_stack_explanation(
        stack_plan=stack_plan,
        user_message=user_msg,
        docs=docs
    )
    
    return {
        "stack_plan": stack_plan.dict(),
        "explanation": explanation,
        "retrieved_count": len(docs),
        "thread_id": request.thread_id
    }

@api.get("/stack/creatine-forms")
def get_creatine_forms():
    """
    Get detailed comparison of creatine forms.
    
    Useful for users asking "which creatine should I take?"
    """
    if not CONVERSATIONAL_STACK_AVAILABLE:
        return {"error": "Not available"}
    
    return get_creatine_form_comparison()

def _compose_stack_explanation(stack_plan: StackPlan, user_message: str, docs: List[dict]) -> str:
    """
    Use LLM to compose a conversational explanation of the stack.
    
    Args:
        stack_plan: The generated stack plan
        user_message: User's question/request
        docs: Retrieved research papers
        
    Returns:
        Conversational explanation with citations
    """
    # Build context from stack items
    items_summary = []
    for item in stack_plan.items:
        dose_str = f"{item.doses[0].value} {item.doses[0].unit}" if item.doses else "varied"
        items_summary.append(f"- {item.supplement.title()}: {dose_str} ({item.evidence_grade})")
    
    # Build context from exclusions
    exclusions_str = ""
    if stack_plan.exclusions:
        exclusions_str = f"\n\nExcluded:\n" + "\n".join(f"- {ex}" for ex in stack_plan.exclusions)
    
    # Build warnings context
    warnings_str = ""
    if stack_plan.warnings:
        warnings_str = f"\n\nSafety Notes:\n" + "\n".join(f"- {w}" for w in stack_plan.warnings)
    
    # Create prompt for LLM
    prompt = f"""Based on the user's question and their profile, explain this supplement stack in a conversational, evidence-based way.

User asked: "{user_message}"

Profile: {stack_plan.profile.goal}, {stack_plan.profile.weight_kg}kg, caffeine_sensitive={stack_plan.profile.caffeine_sensitive}

Recommended Stack:
{chr(10).join(items_summary)}{exclusions_str}{warnings_str}

Provide a conversational explanation that:
1. Directly addresses their question
2. Explains why each supplement is included (briefly)
3. Notes any exclusions and why
4. Highlights key safety considerations
5. Keeps a friendly but professional tone
6. References evidence grades (A=strong, B=moderate, C=limited)

If they asked about specific supplement forms (like creatine), explain the differences.

Keep response under 400 tokens. Be helpful and actionable."""

    try:
        # Use existing foundry_chat function
        response = foundry_chat(prompt, model=FOUNDATION_CHAT_MODEL, max_tokens=400)
        return response
    except Exception as e:
        print(f"LLM composition failed: {e}")
        # Fallback to simple summary
        return f"Based on your profile and question, here's your personalized stack:\n\n" + "\n".join(items_summary)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host=HOST, port=PORT)
