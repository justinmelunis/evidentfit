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
            # === CORE IDENTIFIERS ===
            {"name":"id","type":"Edm.String","key":True},
            {"name":"pmid","type":"Edm.String"},
            {"name":"doi","type":"Edm.String"},
            {"name":"url_pub","type":"Edm.String"},
            
            # === SEARCHABLE CONTENT ===
            {"name":"title","type":"Edm.String","searchable":True},
            {"name":"content","type":"Edm.String","searchable":True},
            {"name":"summary","type":"Edm.String","searchable":True},
            
            # === PUBLICATION METADATA ===
            {"name":"journal","type":"Edm.String"},
            {"name":"year","type":"Edm.Int32"},
            {"name":"study_type","type":"Edm.String"},
            
            # === SUPPLEMENT & OUTCOME TAGS ===
            {"name":"supplements","type":"Edm.String"},
            {"name":"outcomes","type":"Edm.String"},
            
            # === GOAL-SPECIFIC OUTCOMES ===
            {"name":"primary_goal","type":"Edm.String"},
            {"name":"hypertrophy_outcomes","type":"Edm.String"},
            {"name":"weight_loss_outcomes","type":"Edm.String"},
            {"name":"strength_outcomes","type":"Edm.String"},
            {"name":"performance_outcomes","type":"Edm.String"},
            
            # === STUDY METADATA ===
            {"name":"population","type":"Edm.String"},
            {"name":"sample_size","type":"Edm.Int32"},
            {"name":"study_duration","type":"Edm.String"},
            {"name":"sample_size_category","type":"Edm.String"},
            {"name":"duration_category","type":"Edm.String"},
            {"name":"population_category","type":"Edm.String"},
            
            # === AUTHOR & CREDIBILITY ===
            {"name":"first_author","type":"Edm.String"},
            {"name":"author_count","type":"Edm.Int32"},
            {"name":"funding_sources","type":"Edm.String"},
            
            # === SAFETY & DOSAGE ===
            {"name":"safety_indicators","type":"Edm.String"},
            {"name":"dosage_info","type":"Edm.String"},
            {"name":"has_loading_phase","type":"Edm.Boolean"},
            {"name":"has_maintenance_phase","type":"Edm.Boolean"},
            {"name":"has_side_effects","type":"Edm.Boolean"},
            {"name":"has_contraindications","type":"Edm.Boolean"},
            
            # === CATEGORIZATION ===
            {"name":"mesh_terms","type":"Edm.String"},
            {"name":"keywords","type":"Edm.String"},
            
            # === QUALITY & SCORING ===
            {"name":"reliability_score","type":"Edm.Double"},
            {"name":"study_design_score","type":"Edm.Double"},
            {"name":"combination_score","type":"Edm.Double"},
            {"name":"enhanced_score","type":"Edm.Double"},
            
            # === SYSTEM FIELDS ===
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
        r = c.post(url, json=payload)
        if r.status_code != 200:
            print(f"Error response: {r.text}")
        r.raise_for_status()

def get_doc(doc_id: str) -> dict | None:
    headers = {"api-key": ADMIN_KEY}
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/{doc_id}?api-version={API_VERSION}"
    with _client(headers) as c:
        r = c.get(url)
        return r.json() if r.status_code == 200 else None

def search_docs(query: str, top: int = 50) -> dict:
    """Search documents in the index"""
    headers = {"api-key": ADMIN_KEY, "Content-Type": "application/json"}
    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/search?api-version={API_VERSION}"
    payload = {"search": query, "top": top}
    with _client(headers) as c:
        r = c.post(url, json=payload)
        r.raise_for_status()
        return r.json()
