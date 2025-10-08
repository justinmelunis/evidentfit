# EvidentFit API

FastAPI service providing research chat, supplement summaries, and the stack recommender.

## Quick start
```bash
cd api
pip install -r requirements.txt
# Run
python main.py
# or
uvicorn main:api --reload --host 0.0.0.0 --port 8000
```

## Environment
Set via env or Azure Key Vault references:

- `FOUNDATION_ENDPOINT` — Azure AI Foundry Project endpoint
- `FOUNDATION_KEY` — Project API key (header `api-key`)
- `FOUNDATION_CHAT_MODEL` — default `gpt-4o-mini`
- `FOUNDATION_EMBED_MODEL` — default `text-embedding-3-small`
- `SEARCH_ENDPOINT`, `SEARCH_QUERY_KEY`
- `SEARCH_INDEX` (default `evidentfit-index`)
- `SEARCH_SUMMARIES_INDEX` (default `evidentfit-summaries`)
- `INDEX_VERSION` (e.g., `v1-2025-09-25`)
- `CORS_ALLOW_ORIGINS` (comma-separated)
- `DEMO_USER`, `DEMO_PW` (basic preview gate)

## Endpoints
- `GET /healthz` — readiness & liveness
- `POST /stream` — SSE research chat; cites only retrieved docs
- `GET /summaries/{supplement}` — public supplement summaries
- `POST /stack` — deterministic stack by profile (banked where available)
- `GET /stack/bucket/{bucket_key}` — retrieve banked stack
- `GET /stack/buckets` — list known buckets (placeholder)
- `POST /stack/conversational` — Agent D conversational stack (preview)
- `GET /stack/creatine-forms` — creatine forms comparison
- `GET /supplements/evidence` — Level 1 banking data

## Examples (curl)

```bash
# Health
curl -s http://localhost:8000/healthz | jq

# Summaries (example)
curl -s http://localhost:8000/summaries/creatine | jq

# Stream (SSE-like request; server responds with data: lines)
curl -s -u demo:demo123 \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8000/stream \
  -d '{
    "thread_id":"t1",
    "messages":[{"role":"user","content":"Does creatine help strength?"}],
    "profile":{"goal":"strength","weight_kg":80,"caffeine_sensitive":false,"meds":[]}
  }'

# Deterministic stack
curl -s -H "Content-Type: application/json" \
  -X POST http://localhost:8000/stack \
  -d '{
    "profile":{
      "goal":"strength",
      "weight_kg":80,
      "caffeine_sensitive":false,
      "meds":[],
      "diet_protein_g_per_day":90
    }
  }' | jq
```

## Banking
The API loads Level 1/2 banking caches when available from `agents/banking`. See `agents/banking/README.md` for generating caches.

## Notes
- Azure AI Foundry: always call the Project endpoint with `api-key` header and `?api-version=2024-05-01-preview`.
- Responses include the disclaimer: "Educational only; not medical advice."
