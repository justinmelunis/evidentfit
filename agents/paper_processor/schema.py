"""
Schema helpers for the paper processor (moved from agents.ingest.paper_processor).
"""

import json
import hashlib
from typing import Dict, List, Any, Tuple


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
    "study_type": "unknown",
    "outcome_measures": {
        "strength": [],
        "endurance": [],
        "power": []
    },
    "keywords": [],
    "relevance_tags": [],
    # Enhanced fields for better data capture
    "population_size": None,
    "population_characteristics": {
        "age_mean": None,
        "sex_distribution": None,
        "training_status": None
    },
    "intervention_details": {
        "dose_g_per_day": None,
        "dose_mg_per_kg": None,
        "duration_weeks": None,
        "loading_phase": None,
        "supplement_forms": []
    },
    "effect_sizes": [],  # [{"outcome": "1RM", "value": 0.45, "ci_lower": 0.2, "ci_upper": 0.7, "p_value": 0.02}]
    "safety_details": {
        "adverse_events": [],
        "contraindications": [],
        "safety_grade": None  # A/B/C/D
    },
    "extraction_confidence": None,  # 0-1 score
    "study_quality_score": None  # 1-10
  }


def _minified_json_skeleton() -> str:
    return json.dumps(REQUIRED_FIELDS, ensure_ascii=False, separators=(",", ":"))


def create_dedupe_key(obj: Dict[str, Any]) -> str:
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
    out = dict(REQUIRED_FIELDS)
    out.update(obj or {})

    if isinstance(out.get("title"), str):
        out["title"] = out["title"].strip() or "unknown"
    if isinstance(out.get("journal"), str):
        out["journal"] = out["journal"].strip() or "unknown"
    if not out.get("summary") or not str(out.get("summary")).strip():
        out["summary"] = "unknown"

    for k in ("key_findings", "supplements", "keywords", "relevance_tags", "effect_sizes"):
        out[k] = list(out.get(k) or [])

    om = out.get("outcome_measures") or {}
    out["outcome_measures"] = {
        "strength": list(om.get("strength") or []),
        "endurance": list(om.get("endurance") or []),
        "power": list(om.get("power") or []),
    }

    # Normalize population characteristics
    pc = out.get("population_characteristics") or {}
    out["population_characteristics"] = {
        "age_mean": pc.get("age_mean"),
        "sex_distribution": pc.get("sex_distribution"),
        "training_status": pc.get("training_status")
    }

    # Normalize intervention details
    id = out.get("intervention_details") or {}
    out["intervention_details"] = {
        "dose_g_per_day": id.get("dose_g_per_day"),
        "dose_mg_per_kg": id.get("dose_mg_per_kg"),
        "duration_weeks": id.get("duration_weeks"),
        "loading_phase": id.get("loading_phase"),
        "supplement_forms": list(id.get("supplement_forms") or [])
    }

    # Normalize safety details
    sd = out.get("safety_details") or {}
    out["safety_details"] = {
        "adverse_events": list(sd.get("adverse_events") or []),
        "contraindications": list(sd.get("contraindications") or []),
        "safety_grade": sd.get("safety_grade")
    }

    st = str(out.get("study_type") or "unknown").lower()
    out["study_type"] = st

    out.setdefault("dedupe_key", create_dedupe_key(out))
    return out


def validate_optimized_schema(obj: Dict[str, Any]) -> bool:
    for k in REQUIRED_FIELDS.keys():
        if k not in obj:
            return False
    return True


def _one_shot_example() -> str:
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
        "study_type": "randomized_controlled_trial",
        "outcome_measures": {
            "strength": ["1RM bench press", "1RM squat"],
            "endurance": ["repeated sprint test"],
            "power": []
        },
        "keywords": ["creatine", "strength", "RCT"],
        "relevance_tags": ["performance", "resistance_training"],
        "population_size": 45,
        "population_characteristics": {
            "age_mean": 25.3,
            "sex_distribution": "70% male, 30% female",
            "training_status": "trained"
        },
        "intervention_details": {
            "dose_g_per_day": 5.0,
            "dose_mg_per_kg": 71.4,
            "duration_weeks": 8,
            "loading_phase": "yes",
            "supplement_forms": ["creatine monohydrate"]
        },
        "effect_sizes": [
            {"outcome": "1RM bench press", "value": 0.45, "ci_lower": 0.2, "ci_upper": 0.7, "p_value": 0.02},
            {"outcome": "1RM squat", "value": 0.38, "ci_lower": 0.15, "ci_upper": 0.61, "p_value": 0.03}
        ],
        "safety_details": {
            "adverse_events": ["mild gastrointestinal discomfort (2 participants)"],
            "contraindications": ["kidney disease"],
            "safety_grade": "A"
        },
        "extraction_confidence": 0.85,
        "study_quality_score": 8.2
    }
    return json.dumps(example, ensure_ascii=False)


def create_optimized_prompt(paper: Dict[str, Any]) -> str:
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


