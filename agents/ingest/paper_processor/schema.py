"""
Schema helpers for the paper processor.

This version strengthens prompts to reduce empty/omitted fields and adds
a repair prompt for targeted re-asks when key fields are missing.
"""

import json
import hashlib
from typing import Dict, List, Any, Tuple

# -----------------------------
# Required fields & utilities
# -----------------------------

# NOTE: Keep this list aligned with your UI/use-cases. The model is instructed
# to fill these with concrete values, or 'unknown'/[] if not present.
REQUIRED_FIELDS: Dict[str, Any] = {
    "id": "unknown",
    "title": "unknown",
    "journal": "unknown",
    "year": None,
    "pmid": None,
    "doi": None,
    "summary": "unknown",
    "key_findings": [],
    "supplements": [],
    "evidence_grade": "D",
    "quality_score": 0.0,
    "study_type": "unknown",
    "outcome_measures": {
        "strength": [],
        "endurance": [],
        "power": []
    },
    "keywords": [],
    "relevance_tags": [],
  }

def _minified_json_skeleton() -> str:
    """Return a compact JSON skeleton for the model to follow."""
    return json.dumps(REQUIRED_FIELDS, ensure_ascii=False, separators=(",", ":"))

# -----------------------------
# Dedupe key & normalization
# -----------------------------

def create_dedupe_key(obj: Dict[str, Any]) -> str:
    """Stable dedupe key based on pmid/doi or title+year."""
    pmid = (obj.get("pmid") or "").strip() if isinstance(obj.get("pmid"), str) else obj.get("pmid")
    if pmid:
        return f"pmid_{pmid}"
    doi = (obj.get("doi") or "").strip().lower() if isinstance(obj.get("doi"), str) else obj.get("doi")
    if doi:
        return f"doi_{doi}"
    title = (obj.get("title") or "").strip().lower()
    year = str(obj.get("year") or "")
    basis = f"{title}|{year}"
    return f"hash_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:16]}"

def normalize_data(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize fields into the optimized schema format; ensure required keys exist.
    This doesn't grade quality; it enforces presence and default values.
    """
    out = dict(REQUIRED_FIELDS)  # defaults
    out.update(obj or {})

    # Basic tidy-ups
    if isinstance(out.get("title"), str):
        out["title"] = out["title"].strip() or "unknown"
    if isinstance(out.get("journal"), str):
        out["journal"] = out["journal"].strip() or "unknown"
    if not out.get("summary") or not str(out.get("summary")).strip():
        out["summary"] = "unknown"

    # Ensure lists exist
    for k in ("key_findings", "supplements", "keywords", "relevance_tags"):
        out[k] = list(out.get(k) or [])

    # Outcome measures presence
    om = out.get("outcome_measures") or {}
    out["outcome_measures"] = {
        "strength": list(om.get("strength") or []),
        "endurance": list(om.get("endurance") or []),
        "power": list(om.get("power") or []),
    }

    # Evidence grade normalization
    eg = str(out.get("evidence_grade") or "D").upper()
    if eg not in ("A", "B", "C", "D"):
        eg = "D"
    out["evidence_grade"] = eg

    # Quality score bounds
    try:
        qs = float(out.get("quality_score", 0.0))
    except Exception:
        qs = 0.0
    out["quality_score"] = max(0.0, min(qs, 5.0))

    # Study type
    st = str(out.get("study_type") or "unknown").lower()
    out["study_type"] = st

    # Dedupe key
    out.setdefault("dedupe_key", create_dedupe_key(out))
    return out

def validate_optimized_schema(obj: Dict[str, Any]) -> bool:
    """Lightweight validation that all required keys are present (not grading content)."""
    for k in REQUIRED_FIELDS.keys():
        if k not in obj:
            return False
    return True

# -----------------------------
# Prompt builders
# -----------------------------

def _one_shot_example() -> str:
    """A tiny one-shot that mirrors the schema shape to bias completions."""
    example = {
        "id": "pmid_12345678",
        "title": "Creatine supplementation improves strength in trained adults",
        "journal": "Journal of Sports Nutrition",
        "year": 2020,
        "pmid": "12345678",
        "doi": "10.1000/j.jssn.2020.123",
        "summary": "Randomized controlled trials show moderate-to-large improvements in 1RM and repeated-sprint performance with creatine monohydrate (3–5 g/day, loading optional).",
        "key_findings": [
            "Increased 1RM (bench/squat) vs placebo in 6–12 weeks",
            "Improved repeated-sprint performance",
            "No serious adverse events reported"
        ],
        "supplements": ["creatine monohydrate"],
        "evidence_grade": "A",
        "quality_score": 4.2,
        "study_type": "randomized_controlled_trial",
        "outcome_measures": {
            "strength": ["1RM bench press", "1RM squat"],
            "endurance": ["repeated sprint test"],
            "power": []
        },
        "keywords": ["creatine", "strength", "RCT"],
        "relevance_tags": ["performance", "resistance_training"]
    }
    return json.dumps(example, ensure_ascii=False)

def create_optimized_prompt(paper: Dict[str, Any]) -> str:
    """
    Build a strict prompt that forces a complete JSON object. The model is told to:
      - Fill every required field OR use 'unknown'/[] as appropriate.
      - Return ONLY minified JSON (no prose).
    """
    meta_bits = {
        "title": paper.get("title") or "",
        "journal": paper.get("journal") or "",
        "year": paper.get("year"),
        "pmid": paper.get("pmid"),
        "doi": paper.get("doi"),
        "chunk_idx": paper.get("chunk_idx"),
        "chunk_total": paper.get("chunk_total"),
    }
    content = paper.get("content") or ""
    skeleton = _minified_json_skeleton()
    example = _one_shot_example()

    prompt = (
        "You are a clinical evidence analyst. Extract a structured, Q&A-ready JSON summary from the paper text.\n"
        "RULES:\n"
        "1) Output ONLY minified JSON (no backticks, no explanations).\n"
        "2) Include ALL required fields exactly as in the schema. If information is not present, use 'unknown' (for strings) or [] (for arrays) or null (for year/ids).\n"
        "3) Keep the JSON valid and strictly UTF-8.\n"
        f"SCHEMA (minified skeleton):\n{skeleton}\n"
        "ONE-SHOT EXAMPLE (shape to mirror, values are illustrative only):\n"
        f"{example}\n"
        "METADATA (helpful context — do not copy blindly):\n"
        f"{json.dumps(meta_bits, ensure_ascii=False)}\n"
        "TEXT:\n"
        f"{content}\n"
    )
    return prompt

def create_repair_prompt(missing_fields: List[str], prior_json: Dict[str, Any], paper: Dict[str, Any]) -> str:
    """
    Request ONLY the missing fields; return minified JSON with just those keys.
    """
    content = paper.get("content") or ""
    fields_str = json.dumps(sorted(list(set(missing_fields))), ensure_ascii=False)
    prior = json.dumps(prior_json, ensure_ascii=False, separators=(",", ":"))

    return (
        "The previous JSON was missing required fields. Provide ONLY the missing keys (no extra keys), "
        "as minified JSON. For strings use 'unknown' if absent; for arrays use [] if absent; for year/ids use null if unknown.\n"
        f"MISSING_KEYS: {fields_str}\n"
        f"PRIOR_JSON: {prior}\n"
        "TEXT (for context, keep answer short):\n"
        f"{content}\n"
    )
