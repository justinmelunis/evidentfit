from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SuitabilityRule:
    id: str
    applies_to: List[str]
    profile: Dict[str, Any]
    severity: str  # "hard_stop" | "caution"
    message: str


def load_rules(path: Path) -> List[SuitabilityRule]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: List[SuitabilityRule] = []
    for r in raw:
        out.append(
            SuitabilityRule(
                id=r["id"],
                applies_to=r.get("applies_to", ["*"]),
                profile=r.get("profile", {}),
                severity=r["severity"],
                message=r.get("message", ""),
            )
        )
    return out


def _applies(rule: SuitabilityRule, supplement: str) -> bool:
    return "*" in rule.applies_to or supplement.lower() in [s.lower() for s in rule.applies_to]


def _profile_matches(rule: SuitabilityRule, user_profile: Dict[str, Any]) -> bool:
    # Very small matcher: exact key matches and conditions_any array
    for k, v in rule.profile.items():
        if k == "conditions_any":
            conds = set([c.lower() for c in user_profile.get("conditions", [])])
            target = set([c.lower() for c in v])
            if conds.intersection(target):
                return True
        else:
            if user_profile.get(k) == v:
                return True
    return False


def _downgrade(grade: str) -> str:
    ladder = ["A", "B", "C", "D", "F"]
    try:
        i = ladder.index(grade)
    except ValueError:
        return grade
    return ladder[min(i + 1, len(ladder) - 1)]


def apply_suitability(
    supplement: str,
    intrinsic_grade: str,
    rules: List[SuitabilityRule],
    user_profile: Dict[str, Any],
    max_downgrade: int = 1,
) -> Dict[str, Any]:
    reasons: List[str] = []
    final_grade = intrinsic_grade

    # Hard-stop beats everything
    for r in rules:
        if r.severity != "hard_stop":
            continue
        if _applies(r, supplement) and _profile_matches(r, user_profile):
            return {"final_grade": "F", "suitability": f"Avoid: {r.message}", "reasons": [r.id]}

    # Cautions (single-step downgrade)
    downgraded = 0
    for r in rules:
        if r.severity != "caution":
            continue
        if _applies(r, supplement) and _profile_matches(r, user_profile):
            if downgraded < max_downgrade:
                final_grade = _downgrade(final_grade)
                downgraded += 1
            reasons.append(r.id)

    suitability = "OK"
    if reasons and final_grade != "F":
        suitability = "Caution: " + "; ".join(reasons)

    return {"final_grade": final_grade, "suitability": suitability, "reasons": reasons}


