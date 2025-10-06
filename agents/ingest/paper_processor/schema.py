from typing import Dict, Any, List
import re
from collections import Counter, defaultdict

def create_optimized_prompt(p: Dict[str, Any]) -> str:
    title = p.get("title", "Unknown Title")
    abstract = p.get("content", "")
    supplements = p.get("supplements", "")
    study_type = p.get("study_type", "")
    journal = p.get("journal", "")
    year = p.get("year", "")
    pmid = p.get("pmid", "")
    doi = p.get("doi", "")

    return f"""You are a domain expert. Read the paper below and produce ONLY one JSON object (no prose).
The JSON must follow this schema (all keys required):

{{
  "id": string,
  "title": string,
  "journal": string,
  "year": number|null,
  "doi": string|null,
  "pmid": string|null,

  "study_type": string,
  "study_design": string,

  "population": {{
    "age_range": string,
    "sex": "male"|"female"|"mixed"|"not_reported",
    "training_status": "athletes"|"trained"|"untrained"|"sedentary"|"not_reported",
    "sample_size": number|null
  }},

  "summary": string,                    // 2–5 sentences
  "key_findings": [string],             // bullet-style distilled facts

  "supplements": [string],              // list of supplements tested/referenced
  "supplement_primary": string|null,    // main supplement focus if any

  "dosage": {{
    "loading": string|null,
    "maintenance": string|null,
    "timing": string|null,
    "form": string|null
  }},

  "primary_outcome": string,            // strength | endurance | power | weight_loss | performance | general
  "outcome_measures": {{
    "strength": [string],
    "endurance": [string],
    "power": [string]
  }},

  "safety_issues": [string],
  "adverse_events": string|null,

  "evidence_grade": "A"|"B"|"C"|"D",
  "quality_score": number,              // 0–10

  "limitations": [string],
  "clinical_relevance": string,

  "keywords": [string],
  "relevance_tags": [string]
}}

Use concise, unambiguous language. If unknown, use null or "not_reported".
Paper metadata:
  title: {title}
  journal: {journal}
  year: {year}
  pmid: {pmid}
  doi: {doi}
  supplements_hint: {supplements}
  study_type_hint: {study_type}

Abstract:
{abstract}
"""

def validate_optimized_schema(d: Dict[str, Any]) -> bool:
    required = [
        "id","title","journal","year","doi","pmid",
        "study_type","study_design","population","summary","key_findings",
        "supplements","supplement_primary","dosage","primary_outcome",
        "outcome_measures","safety_issues","adverse_events",
        "evidence_grade","quality_score","limitations","clinical_relevance",
        "keywords","relevance_tags"
    ]
    for k in required:
        if k not in d:
            return False
    if not isinstance(d.get("key_findings"), list): return False
    if not isinstance(d.get("supplements"), list): return False
    if not isinstance(d.get("outcome_measures"), dict): return False
    if not isinstance(d.get("population"), dict): return False
    if not isinstance(d.get("limitations"), list): return False
    if not isinstance(d.get("keywords"), list): return False
    if not isinstance(d.get("relevance_tags"), list): return False
    if not isinstance(d.get("quality_score"), (int, float)): return False
    if d.get("evidence_grade") not in {"A","B","C","D"}: return False
    return True

def normalize_data(d: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(d)
    # year → int|null
    y = d.get("year")
    if isinstance(y, str):
        m = re.search(r"\d{4}", y)
        d["year"] = int(m.group(0)) if m else None
    # lists
    for k in ["key_findings","supplements","limitations","keywords","relevance_tags"]:
        v = d.get(k)
        if v is None: d[k] = []
        elif not isinstance(v, list): d[k] = [v]
    # outcome_measures shape
    om = d.get("outcome_measures") or {}
    d["outcome_measures"] = {
        "strength": list(om.get("strength", []) or []),
        "endurance": list(om.get("endurance", []) or []),
        "power": list(om.get("power", []) or []),
    }
    # population defaults
    pop = d.get("population") or {}
    d["population"] = {
        "age_range": pop.get("age_range") or "not_reported",
        "sex": pop.get("sex") or "not_reported",
        "training_status": pop.get("training_status") or "not_reported",
        "sample_size": pop.get("sample_size") if isinstance(pop.get("sample_size"), (int,float)) else None,
    }
    # dosage defaults
    doz = d.get("dosage") or {}
    d["dosage"] = {
        "loading": doz.get("loading"),
        "maintenance": doz.get("maintenance"),
        "timing": doz.get("timing"),
        "form": doz.get("form"),
    }
    # quality bounds
    try:
        qs = float(d.get("quality_score", 0.0))
    except Exception:
        qs = 0.0
    d["quality_score"] = max(0.0, min(10.0, qs))
    # id/title fallbacks
    d["id"] = str(d.get("id") or d.get("pmid") or d.get("doi") or "unknown")
    d["title"] = d.get("title") or "Unknown Title"
    d["journal"] = d.get("journal") or "Unknown Journal"
    # primary_outcome guard
    d["primary_outcome"] = d.get("primary_outcome") or "general"
    return d

def create_dedupe_key(d: Dict[str, Any]) -> str:
    base = (d.get("pmid") or d.get("doi") or (d.get("title","").lower().strip()))
    return re.sub(r"\W+", "_", base)[:128] if base else "unknown"

def create_search_index(papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    years = []
    st_counts = Counter()
    eg_counts = Counter()
    supp_counts = Counter()

    for p in papers:
        y = p.get("year")
        if isinstance(y, int): years.append(y)
        st_counts[p.get("study_type","unknown")] += 1
        eg_counts[p.get("evidence_grade","D")] += 1
        for s in p.get("supplements", []) or []:
            if s: supp_counts[s] += 1

    stats = {
        "total_papers": len(papers),
        "study_types": dict(st_counts),
        "evidence_grades": dict(eg_counts),
        "year_range": {"min": min(years) if years else None, "max": max(years) if years else None},
        "supplements": dict(supp_counts)
    }
    return {"statistics": stats}
