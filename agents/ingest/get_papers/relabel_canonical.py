"""
Retroactive relabel for data/index/canonical_papers.jsonl.

Adds/updates fields:
- study_type (may upgrade to doc_kind when clearly review/position/guideline)
- doc_kind (position-stand, narrative_review, guideline, consensus, perspective, editorial)
- banking_eligible (False for doc_kind types above)
- study_strength (float [0,1] for ranking)
- reliability_score (adjusted to mapping)
- override_source = "retro-canonical"

Safe behavior:
- Backs up the source file to a timestamped .bak.
- Writes a new relabeled file alongside the original unless --in-place is provided.
"""

from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from datetime import datetime


STUDY_STRENGTH_MAP = {
    "meta-analysis": 1.0,
    "systematic_review": 0.9,
    "RCT": 0.8,
    "crossover": 0.7,
    "cohort": 0.5,
    "case_control": 0.4,
    "narrative_review": 0.2,
    "position-stand": 0.25,
    "guideline": 0.25,
    "consensus": 0.25,
    "perspective": 0.15,
    "editorial": 0.1,
}

RELIABILITY_BY_TYPE = {
    "meta-analysis": 13.0,
    "systematic_review": 11.0,
    "RCT": 10.0,
    "crossover": 7.0,
    "cohort": 4.0,
    "case_control": 3.5,
    "narrative_review": 3.0,
    "position-stand": 4.0,
    "guideline": 4.0,
    "consensus": 4.0,
    "perspective": 2.0,
    "editorial": 2.0,
}

PRIMARY_TYPES = {"meta-analysis", "systematic_review", "RCT", "crossover", "cohort", "case_control", "clinical_trial", "controlled_trial"}
NON_BANKING_TYPES = {"narrative_review", "position-stand", "guideline", "consensus", "perspective", "editorial"}


def detect_doc_kind(title: str, journal: str) -> str | None:
    t = f"{title or ''} {journal or ''}".lower()
    if any(k in t for k in ("position stand", "position statement")):
        return "position-stand"
    if "consensus" in t:
        return "consensus"
    if "guideline" in t or "practice guideline" in t:
        return "guideline"
    if any(k in t for k in ("perspective", "viewpoint", "opinion")):
        return "perspective"
    # Narrative review: has 'review' but not systematic/meta keywords
    if "review" in t and not re.search(r"systematic|meta-?analysis", t):
        return "narrative_review"
    # Editorial
    if "editorial" in t:
        return "editorial"
    return None


def compute_flags(study_type: str, doc_kind: str | None):
    label = doc_kind or study_type
    strength = STUDY_STRENGTH_MAP.get(label, STUDY_STRENGTH_MAP.get(study_type, 0.3))
    banking_eligible = label not in NON_BANKING_TYPES
    reliability = RELIABILITY_BY_TYPE.get(label, RELIABILITY_BY_TYPE.get(study_type, 3.0))
    return banking_eligible, strength, reliability


def relabel_line(obj: dict, conservative: bool = True) -> dict:
    title = obj.get("title", "")
    journal = obj.get("journal", "")
    old_type = (obj.get("study_type") or "").strip()
    # Normalize hyphen variants
    old_type_norm = old_type.replace("-", "_")

    doc_kind = detect_doc_kind(title, journal)
    new_type = old_type

    # Precedence: keep strong primary labels unless it's explicitly a position/guideline/consensus
    if doc_kind in {"position-stand", "guideline", "consensus", "editorial", "perspective"}:
        new_type = doc_kind
    elif doc_kind == "narrative_review":
        if conservative and old_type_norm in PRIMARY_TYPES:
            # keep primary label
            new_type = old_type
        else:
            new_type = doc_kind

    banking_eligible, study_strength, reliability_score = compute_flags(new_type, doc_kind)

    obj["doc_kind"] = doc_kind
    obj["study_type"] = new_type
    obj["banking_eligible"] = banking_eligible
    obj["study_strength"] = study_strength
    obj["reliability_score"] = reliability_score
    obj["override_source"] = "retro-canonical"
    return obj


def main():
    ap = argparse.ArgumentParser(description="Retro relabel canonical_papers.jsonl")
    ap.add_argument("--src", default=str(Path("data/index/canonical_papers.jsonl")), help="Source canonical JSONL")
    ap.add_argument("--out", default=None, help="Output path (default: canonical_papers.relabel.jsonl next to src)")
    ap.add_argument("--in-place", action="store_true", help="Overwrite source in place (after .bak created)")
    ap.add_argument("--strict", action="store_true", help="Allow narrative_review to replace weak/other study types")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")

    # Backup
    bak = src.with_suffix(src.suffix + ".bak_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    bak.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    out = Path(args.out) if args.out else src.with_name(src.stem + ".relabel.jsonl")

    n_total = 0
    n_changed = 0
    with src.open("r", encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            n_total += 1
            old = (obj.get("study_type") or "")
            new_obj = relabel_line(obj, conservative=not args.strict)
            new = new_obj.get("study_type")
            if new != old:
                n_changed += 1
            fout.write(json.dumps(new_obj, ensure_ascii=False) + "\n")

    print(f"Relabeled: {n_changed}/{n_total} → {out}")

    if args.in_place:
        src.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Overwrote source with relabeled output. Backup at {bak}")


if __name__ == "__main__":
    main()


