from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Optional import; we will no-op if not present
try:
    from .mistral_client import MistralClient  # local module in this package
except Exception:  # pragma: no cover
    MistralClient = None  # type: ignore

DOSE_NEAR_WINDOW = 160  # characters within the term window
METRICS_PATH_DEFAULT = Path("data/cards/_logs/extract_metrics.jsonl")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    tmp.replace(path)


def _rx(pattern: str, flags=re.I | re.M):
    return re.compile(pattern, flags)


_RX_N = _rx(r"\b(n|sample size|participants)\s*[:=]?\s*(\d{2,4})\b")
_RX_DURATION = _rx(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:wk|wks|week|weeks|mo|mos|month|months)\b")
_RX_DOSE = _rx(r"\b(\d+(?:\.\d+)?)\s*(g|mg)\s*/\s*(?:d|day|kg)\b")


def _heuristics(bundle: dict) -> dict:
    """
    Very light regex-based extraction as a baseline.
    """
    log = logging.getLogger("paper_processor.extract")
    methods = (bundle["sections"].get("methods") or {}).get("text", "") or ""
    abstract = (bundle["sections"].get("abstract") or {}).get("text", "") or ""
    results = (bundle["sections"].get("results") or {}).get("text", "") or ""
    discussion = (bundle["sections"].get("discussion") or {}).get("text", "") or ""

    text_for_n = f"{methods}\n\n{abstract}"
    n = None
    m = _RX_N.search(text_for_n)
    if m:
        try:
            n = int(m.group(2))
        except Exception:
            n = None
    if n is None:
        log.debug("population.n not detected via heuristics")

    duration_weeks = None
    m = _RX_DURATION.search(methods or abstract)
    if m:
        val = float(m.group(1))
        unit = m.group(0).lower()
        if "mo" in unit or "month" in unit:
            duration_weeks = int(round(val * 4.345))  # approx convert months→weeks
        else:
            duration_weeks = int(round(val))
    else:
        log.debug("intervention.duration_weeks not detected via heuristics")

    dose_g_per_day = None
    # If supplement name present, search a window near it; else global
    supp_terms = bundle.get("meta", {}).get("supplements") or []
    context = methods or abstract
    if supp_terms:
        base = context.lower()
        hit_ix = -1
        for term in supp_terms:
            ix = base.find(str(term).lower())
            if ix >= 0:
                hit_ix = ix
                break
        if hit_ix >= 0:
            window = context[max(0, hit_ix - DOSE_NEAR_WINDOW) : hit_ix + DOSE_NEAR_WINDOW]
            m = _RX_DOSE.search(window)
        else:
            m = _RX_DOSE.search(context)
    else:
        m = _RX_DOSE.search(context)
    if m:
        val = float(m.group(1))
        unit = m.group(2).lower()
        # Normalize to grams/day
        dose_g_per_day = val / 1000.0 if unit == "mg" else val
    else:
        log.debug("intervention.dose_g_per_day not detected near supplement mention")

    # Naive outcomes direction from results keywords
    outcomes = []
    if results:
        lower = results.lower()
        direction = None
        incr_hits = ["increase", "increased", "improved", "improvement", "greater than placebo"]
        decr_hits = ["decrease", "decreased", "reduced", "reduction", "less than placebo"]
        noeff_hits = ["no significant", "no effect", "ns.", "n.s."]
        if any(tok in lower for tok in incr_hits):
            direction = "increase"
        elif any(tok in lower for tok in decr_hits):
            direction = "decrease"
        elif any(tok in lower for tok in noeff_hits):
            direction = "no_effect"
        if direction:
            # provenance span: take first keyword occurrence
            span_start = -1
            first_token = None
            for tok in (incr_hits + decr_hits + noeff_hits):
                ix = lower.find(tok)
                if ix >= 0:
                    span_start = ix
                    first_token = tok
                    break
            span = [max(0, span_start), max(0, span_start + (len(first_token) if span_start >= 0 and first_token else 0))]
            first_chunk = (bundle["sections"].get("results") or {}).get("chunks") or []
            outcomes.append(
                {
                    "name": "primary outcome",
                    "domain": bundle.get("meta", {}).get("primary_goal") or "unknown",
                    "direction": direction,
                    "effect_size_norm": None,  # unknown here
                    "p_value": None,
                    "notes": None,
                    "provenance": (
                        [{"chunk_id": first_chunk[0], "span": span}] if first_chunk and span_start >= 0 else []
                    ),
                }
            )
            logging.getLogger("paper_processor.extract").info(
                "Outcome inferred from RESULTS keywords: domain=%s direction=%s",
                bundle.get("meta", {}).get("primary_goal") or "unknown",
                direction,
            )
        else:
            logging.getLogger("paper_processor.extract").info("No clear outcome direction found in RESULTS")

    safety_notes = None
    if discussion or results:
        lower = (discussion + "\n" + results).lower()
        if "adverse" in lower:
            safety_notes = "adverse events discussed"
        elif "no serious adverse" in lower:
            safety_notes = "no serious adverse events reported"
    if safety_notes is None:
        logging.getLogger("paper_processor.extract").debug("safety.notes not detected")

    return {
        "population": {"n": n, "sex": None, "age": None},
        "intervention": {
            "dose_g_per_day": dose_g_per_day,
            "loading": None,
            "duration_weeks": duration_weeks,
            "comparator": None,
        },
        "outcomes": outcomes,
        "safety": {"notes": safety_notes, "contraindications": [], "provenance": []},
    }


def _llm_enrich(bundle: dict, model_ver: str, prompt_ver: str) -> Optional[dict]:
    """
    Optional LLM pass A (basic enrichment).
    If MistralClient is not available, returns None and we keep heuristics only.
    """
    if MistralClient is None:
        return None
    client = MistralClient(model_name=model_ver)
    prompt_path = Path("agents/paper_processor/prompts/card_extractor_v1.txt")
    prompt = prompt_path.read_text(encoding="utf-8")
    # Small input: abstract+results (+methods if short)
    abstract = (bundle["sections"].get("abstract") or {}).get("text", "") or ""
    results = (bundle["sections"].get("results") or {}).get("text", "") or ""
    methods = (bundle["sections"].get("methods") or {}).get("text", "") or ""
    context = f"ABSTRACT:\n{abstract}\n\nRESULTS:\n{results}\n\nMETHODS:\n{methods[:4000]}"
    sysmsg = "You are an expert evidence extraction engine. Output strict JSON only."
    usermsg = prompt.replace("{{CONTEXT}}", context)[:12000]
    out = client.generate_json(system_prompt=sysmsg, user_prompt=usermsg, max_new_tokens=1024)
    # Expect out to match portions of Evidence Card (population, intervention, outcomes, safety)
    return out if isinstance(out, dict) else None


def _slice_for(bundle: dict, keys: List[str]) -> Tuple[str, List[str]]:
    """Return excerpt text and its chunk ids for the requested keys."""
    text_parts, chunk_ids = [], []
    for k in keys:
        sec = (bundle["sections"].get(k) or {})
        if sec.get("text"):
            text_parts.append(f"{k.upper()}:\n{sec['text']}")
            chunk_ids.extend(sec.get("chunks") or [])
    return ("\n\n".join(text_parts)[:12000], chunk_ids)


def _validate_prov(span: List[int], excerpt_len: int) -> bool:
    if not isinstance(span, list) or len(span) != 2:
        return False
    s, e = span
    return 0 <= s < e <= max(0, excerpt_len)


def _llm_fallback(bundle: dict, want_population: bool, want_intervention: bool, want_outcomes: bool, want_safety: bool,
                  model_ver: str, prompt_ver: str) -> Optional[dict]:
    """Targeted fallback: ask only for missing sections using smaller, relevant context."""
    if MistralClient is None:
        return None
    client = MistralClient(model_name=model_ver)
    # Build minimal excerpt
    need_sections = []
    if want_outcomes or want_safety:
        need_sections += ["results"]
    if want_safety:
        need_sections += ["discussion"]
    if want_population or want_intervention:
        need_sections += ["methods"]
    excerpt, _ = _slice_for(bundle, list(dict.fromkeys(need_sections)))
    if not excerpt.strip():
        return None
    sysmsg = "You are extracting ONLY the fields requested. Output strict JSON. If unknown, use null or []."
    # Short, field-scoped prompt
    fields = []
    if want_population:
        fields.append("population")
    if want_intervention:
        fields.append("intervention")
    if want_outcomes:
        fields.append("outcomes")
    if want_safety:
        fields.append("safety")
    ask = ", ".join(fields)
    usermsg = (
        f"From the excerpt below, extract ONLY these fields: {ask}.\n"
        "Rules:\n"
        "- Provide provenance for each filled item as {chunk_id, span}.\n"
        "- span MUST reference character offsets within THIS excerpt.\n"
        "- If a value is not explicitly supported, set it to null (or []), do not guess.\n\n"
        f"EXCERPT:\n{excerpt}"
    )
    out = client.generate_json(system_prompt=sysmsg, user_prompt=usermsg, max_new_tokens=768)
    # Validate spans: ensure all provided spans fall within excerpt range
    if isinstance(out, dict):
        elen = len(excerpt)
        def clean_prov(provs):
            good = []
            for p in provs or []:
                span = p.get("span")
                if _validate_prov(span, elen):
                    good.append(p)
            return good
        if "outcomes" in out and isinstance(out["outcomes"], list):
            for oc in out["outcomes"]:
                oc["provenance"] = clean_prov(oc.get("provenance"))
        if "safety" in out and isinstance(out["safety"], dict):
            out["safety"]["provenance"] = clean_prov(out["safety"].get("provenance"))
        return out
    return None


def _append_metrics(before: dict, after: dict, used_fallback: bool, metrics_path: Path) -> None:
    try:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "paper_id": after.get("meta", {}).get("pmid") or after.get("paper_id"),
            "used_fallback": used_fallback,
            "before": before,
            "after": {
                "population_has_n": (after.get("population") or {}).get("n") is not None,
                "intervention_has_dose": (after.get("intervention") or {}).get("dose_g_per_day") is not None,
                "intervention_has_duration": (after.get("intervention") or {}).get("duration_weeks") is not None,
                "outcomes_len": len(after.get("outcomes") or []),
                "safety_has_notes": bool((after.get("safety") or {}).get("notes")),
                "outcomes_with_prov": sum(1 for o in (after.get("outcomes") or []) if o.get("provenance")),
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def build_card(bundle: dict, model_ver: str = "mistral-7b-instruct", prompt_ver: str = "v1",
               llm_mode: str = "fallback", metrics_path: Path = METRICS_PATH_DEFAULT) -> dict:
    log = logging.getLogger("paper_processor.extract")
    base = _heuristics(bundle)
    enriched = None
    if llm_mode in ("basic", "fallback"):
        enriched = _llm_enrich(bundle, model_ver=model_ver, prompt_ver=prompt_ver)
    merged = base.copy()
    if isinstance(enriched, dict):
        # shallow merge for known keys
        for k in ("population", "intervention", "outcomes", "safety"):
            if k in enriched and enriched[k]:
                merged[k] = enriched[k]
    else:
        log.info("LLM enrich skipped or unavailable; using heuristic_v1 only")

    meta = bundle.get("meta", {})
    # Auto keywords/tags
    supplements = meta.get("supplements") or []
    primary_goal = meta.get("primary_goal")
    keywords = list({*(s for s in supplements), *(filter(None, [primary_goal]))})
    relevance_tags = []
    if primary_goal:
        relevance_tags.append(primary_goal)
    # Auto summary (very short)
    summary = None
    if merged.get("outcomes"):
        d = merged["outcomes"][0].get("direction")
        if primary_goal and d in ("increase", "decrease", "no_effect"):
            verb = {"increase": "improves", "decrease": "reduces", "no_effect": "shows no clear effect on"}[d]
            summary = f"{(supplements[0] if supplements else 'Supplement').title()} {verb} {primary_goal.replace('_',' ')}."
    card = {
        "paper_id": f"pmid_{bundle['paper_id']}",
        "meta": {
            "title": meta.get("title"),
            "journal": meta.get("journal"),
            "year": meta.get("year"),
            "pmid": meta.get("pmid") or bundle["paper_id"],
            "doi": meta.get("doi"),
            "study_type": (meta.get("study_type") or "").replace(" ", "_").lower() if meta.get("study_type") else None,
            "primary_goal": meta.get("primary_goal"),
            "supplements": meta.get("supplements") or [],
            "reliability_score": meta.get("reliability_score"),
        },
        "population": merged.get("population"),
        "intervention": merged.get("intervention"),
        "outcomes": merged.get("outcomes") or [],
        "safety": merged.get("safety") or {"notes": None, "contraindications": [], "provenance": []},
        "summary": summary,
        "keywords": keywords,
        "relevance_tags": relevance_tags,
        "generator": {
            "mode": "llm_enrich_v1" if enriched else "heuristic_v1",
            "model_ver": model_ver,
            "prompt_ver": prompt_ver,
            "input_hash": bundle.get("input_hash"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    # Emit a concise log about empties to help QA
    empties = []
    if card["population"]["n"] is None:
        empties.append("population.n")
    if card["intervention"]["dose_g_per_day"] is None:
        empties.append("intervention.dose_g_per_day")
    if card["intervention"]["duration_weeks"] is None:
        empties.append("intervention.duration_weeks")
    if not card["outcomes"]:
        empties.append("outcomes[]")
    if not card["safety"]["notes"]:
        empties.append("safety.notes")
    if empties:
        log.info("Sparse fields: %s", ", ".join(empties))

    # Targeted fallback if requested and still missing key fields
    used_fallback = False
    if llm_mode == "fallback":
        need_pop = (card["population"] or {}).get("n") is None
        need_intv = (card["intervention"] or {}).get("dose_g_per_day") is None or (card["intervention"] or {}).get("duration_weeks") is None
        need_outc = not card.get("outcomes")
        need_safe = not card.get("safety", {}).get("notes")
        before = {
            "population_has_n": not need_pop,
            "intervention_has_any": not need_intv,
            "has_outcomes": not need_outc,
            "safety_has_notes": not need_safe,
        }
        if any([need_pop, need_intv, need_outc, need_safe]):
            fb = _llm_fallback(bundle, need_pop, need_intv, need_outc, need_safe, model_ver, prompt_ver)
            if isinstance(fb, dict):
                # Merge only fields we asked for; require provenance for outcomes
                if need_pop and fb.get("population"):
                    card["population"] = {**(card["population"] or {}), **fb["population"]}
                if need_intv and fb.get("intervention"):
                    card["intervention"] = {**(card["intervention"] or {}), **fb["intervention"]}
                if need_outc and isinstance(fb.get("outcomes"), list):
                    with_prov = [o for o in fb["outcomes"] if o.get("provenance")]
                    if with_prov:
                        card["outcomes"] = with_prov
                if need_safe and isinstance(fb.get("safety"), dict):
                    if fb["safety"].get("notes"):
                        card["safety"]["notes"] = fb["safety"].get("notes")
                        card["safety"]["provenance"] = fb["safety"].get("provenance") or []
                used_fallback = True
                _append_metrics(before, card, used_fallback, metrics_path)
            else:
                _append_metrics(before, card, used_fallback, metrics_path)
        else:
            _append_metrics({"no_need": True}, card, used_fallback, metrics_path)
    return card


def write_card(card: dict, dest_dir: Path) -> Path:
    out_path = dest_dir / f"{card['meta']['pmid']}.json"
    _atomic_write_json(out_path, card)
    return out_path


if __name__ == "__main__":
    # Quick manual smoke:
    # python -m agents.paper_processor.extract data/cards/_raw/33562750.json
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_path")
    parser.add_argument("--outdir", default="data/cards")
    parser.add_argument("--model", default="mistral-7b-instruct")
    parser.add_argument("--prompt-ver", default="v1")
    args = parser.parse_args()
    bundle = json.loads(Path(args.bundle_path).read_text())
    card = build_card(bundle, model_ver=args.model, prompt_ver=args.prompt_ver)
    path = write_card(card, Path(args.outdir))
    print(str(path))



