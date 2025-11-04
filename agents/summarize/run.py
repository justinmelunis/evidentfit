"""
Agent D (Summarizer): Compose supplement summaries using Papers index and Level 1 banking grades.

Outputs a simple JSON file per supplement under data/summaries/ with fields that match the
expected Summaries index schema. Evidence grade is sourced from Level 1 banking.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

def _resolve_search():
    # Prefer shared search client; else fall back to API local client via sys.path hack
    try:
        from evidentfit_shared.search_client import search_docs as sd  # type: ignore
        return sd
    except Exception:
        import sys
        from pathlib import Path as _P
        here = _P(__file__).resolve()
        # Walk up to repo root by looking for 'evidentfit' folder name
        cur = here.parent
        repo_root = None
        while cur != cur.parent:
            if cur.name == 'evidentfit':
                repo_root = cur
                break
            cur = cur.parent
        if repo_root is None:
            repo_root = here.parents[3] if len(here.parents) >= 4 else here.parent.parent
        sys.path.append(str(repo_root))
        from api.clients.search_read import search_docs as sd  # type: ignore
        return sd

search_docs = _resolve_search()


def _load_level1_bank() -> Dict:
    """Load Level 1 bank from agents/banking/ if available."""
    candidates = [
        Path(__file__).resolve().parent.parent / "banking" / "level1_evidence_bank.json",
        Path("level1_evidence_bank.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _grade_for_supplement_from_level1(level1: Dict, supplement: str) -> str:
    """Pick the strongest (best) grade across all goals for a supplement."""
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    best = ("D", 1)
    if not level1:
        return "D"
    # Accept both flat and nested under evidence_data
    data = level1
    if isinstance(level1, dict) and "evidence_data" in level1:
        data = level1["evidence_data"]
    if not isinstance(data, dict):
        return "D"
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # Keys may be "goal:supplement" or "supplement:goal" depending on producer
        parts = str(key).split(":")
        if len(parts) == 2:
            if supplement.lower() not in (parts[0].lower(), parts[1].lower()):
                continue
        elif str(entry.get("supplement", "")).lower() != supplement.lower():
            continue
        g = str(entry.get("grade", "D")).upper()
        score = grade_order.get(g, 1)
        if score > best[1]:
            best = (g, score)
    return best[0]


def _compose_overview_md(supplement: str, docs: List[dict], grade: str) -> str:
    lines = [f"# {supplement.title()} — Evidence grade: {grade}", "", "Key papers:"]
    for d in docs[:6]:
        title = d.get("title", "")
        journal = d.get("journal", "")
        year = d.get("year", "")
        pmid = d.get("pmid", "")
        url = d.get("url_pub", "")
        lines.append(f"- {title} ({journal} {year}) PMID:{pmid} {url}")
    return "\n".join(lines)


def _compose_last12_md(docs: List[dict]) -> str:
    if not docs:
        return "No recent papers found."
    lines = ["## Last 12 months", ""]
    for d in docs[:6]:
        lines.append(f"- {d.get('title','')} ({d.get('journal','')} {d.get('year','')})")
    return "\n".join(lines)


def build_supplement_summary(supplement: str, level1: Dict) -> Dict:
    # Pull grade from Level 1
    grade = _grade_for_supplement_from_level1(level1, supplement)

    # Retrieve papers for overview/recent sections
    try:
        hits = search_docs(query=supplement, top=20)
        docs = hits if isinstance(hits, list) else hits.get("value", [])
    except Exception:
        docs = []

    overview_md = _compose_overview_md(supplement, docs, grade)
    last12_md = _compose_last12_md(docs)

    # Build citations JSON strings
    key_papers = []
    for p in docs[:8]:
        if p.get("title"):
            key_papers.append({
                "title": p.get("title",""),
                "doi": p.get("doi",""),
                "pmid": p.get("pmid",""),
                "url": p.get("url_pub",""),
                "journal": p.get("journal",""),
                "year": p.get("year",""),
                "study_type": p.get("study_type",""),
            })

    out = {
        "id": f"summary:{supplement}",
        "supplement": supplement,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "overview_md": overview_md,
        "last12_md": last12_md,
        "key_papers_json": json.dumps(key_papers, ensure_ascii=False),
        "recent_papers_json": json.dumps(key_papers[:6], ensure_ascii=False),
        "evidence_grade": grade,
        "index_version": os.getenv("INDEX_VERSION", "v1"),
    }
    return out


def main():
    supplements = [
        "creatine", "protein", "caffeine", "beta-alanine", "citrulline",
        "nitrate", "hmb", "bcaa", "taurine", "carnitine", "glutamine",
    ]
    level1 = _load_level1_bank()
    outdir = Path("data/summaries")
    outdir.mkdir(parents=True, exist_ok=True)

    for supp in supplements:
        summary = build_supplement_summary(supp, level1)
        out_path = outdir / f"summary_{supp}.json"
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()


