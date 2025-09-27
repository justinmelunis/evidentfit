import os, httpx

API_VERSION = "2023-11-01"
SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "").rstrip("/")
SEARCH_INDEX = os.getenv("SEARCH_INDEX", "evidentfit-index")
ADMIN_KEY = os.getenv("SEARCH_ADMIN_KEY")

# Validate required environment variables
if not SEARCH_ENDPOINT:
    raise RuntimeError("SEARCH_ENDPOINT environment variable is required")
if not ADMIN_KEY:
    raise RuntimeError("SEARCH_ADMIN_KEY environment variable is required")

def _client(headers): return httpx.Client(timeout=60, headers=headers)

def ensure_index(vector_dim: int = 1536):
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}?api-version={API_VERSION}"
    headers = {"api-key": ADMIN_KEY, "Content-Type": "application/json"}
    with _client(headers) as c:
        r = c.get(url)
        if r.status_code == 200: return
        if r.status_code != 404: r.raise_for_status()
        body = {
          "name": SEARCH_INDEX,
          "fields": [
            {"name":"id","type":"Edm.String","key":True},
            {"name":"title","type":"Edm.String","searchable":True},
            {"name":"doi","type":"Edm.String"},
            {"name":"pmid","type":"Edm.String"},
            {"name":"url_pub","type":"Edm.String"},
            {"name":"journal","type":"Edm.String"},
            {"name":"year","type":"Edm.Int32"},
            {"name":"study_type","type":"Edm.String"},
            {"name":"supplements","type":"Edm.String"},
            {"name":"outcomes","type":"Edm.String"},
            {"name":"population","type":"Edm.String"},
            {"name":"summary","type":"Edm.String","searchable":True},
            {"name":"content","type":"Edm.String","searchable":True},
            {"name":"content_vector","type":"Edm.String"},
            {"name":"index_version","type":"Edm.String"}
          ]
        }
        r = c.put(f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}?api-version={API_VERSION}", json=body)
        r.raise_for_status()

def upsert_docs(docs: list[dict]):
    headers = {"api-key": ADMIN_KEY, "Content-Type": "application/json"}
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/index?api-version={API_VERSION}"
    payload = {"value": [{"@search.action":"mergeOrUpload", **d} for d in docs]}
    with _client(headers) as c:
        r = c.post(url, json=payload); r.raise_for_status()

def get_doc(doc_id: str) -> dict | None:
    headers = {"api-key": ADMIN_KEY}
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/{doc_id}?api-version={API_VERSION}"
    with _client(headers) as c:
        r = c.get(url)
        return r.json() if r.status_code == 200 else None
