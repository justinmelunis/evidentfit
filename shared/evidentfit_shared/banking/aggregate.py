from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml


@dataclass
class BankingConfig:
    design_weights: Dict[str, float]
    w_min: float
    effect_small: float
    effect_b: float
    effect_a: float
    null_eps: float
    negative_thresh: float
    direction_fallback: float

    @classmethod
    def load(cls, path: Path) -> "BankingConfig":
        cfg = yaml.safe_load(path.read_text())
        return cls(
            design_weights=cfg["design_weights"],
            w_min=float(cfg["w_min"]),
            effect_small=float(cfg["cutoffs"]["small"]),
            effect_b=float(cfg["cutoffs"]["b"]),
            effect_a=float(cfg["cutoffs"]["a"]),
            null_eps=float(cfg["null_eps"]),
            negative_thresh=float(cfg["negative_thresh"]),
            direction_fallback=float(cfg["direction_fallback"]),
        )


def _weight(design: str, n: Optional[int], cfg: BankingConfig) -> float:
    base = cfg.design_weights.get(design, 0.5)
    n_val = max(int(n or 0), 0)
    return base * math.log(1.0 + n_val)


def _sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _card_to_effects(card: dict, cfg: BankingConfig) -> List[Tuple[float, float, str]]:
    """
    Returns list of tuples: (w_i, e_i, paper_id)
    """
    design = (card.get("meta", {}).get("study_type") or "").lower()
    n = (card.get("population") or {}).get("n")
    wi = _weight(design, n, cfg)
    pid = str(card.get("meta", {}).get("pmid") or card.get("paper_id") or "unknown")
    out: List[Tuple[float, float, str]] = []
    for oc in card.get("outcomes") or []:
        e = oc.get("effect_size_norm")
        if e is None:
            direction = (oc.get("direction") or "").lower()
            if direction == "increase":
                e = cfg.direction_fallback
            elif direction == "decrease":
                e = -cfg.direction_fallback
            elif direction in ("no_effect", "uncertain"):
                e = 0.0
            else:
                continue
        e = max(min(float(e), 1.0), -1.0)
        out.append((wi, e, pid))
    return out


def _consistency(effects: List[Tuple[float, float, str]]) -> float:
    """
    Weighted fraction sharing pooled sign.
    """
    if not effects:
        return 0.0
    w_sum = sum(w for w, _, __ in effects)
    if w_sum <= 0:
        return 0.0
    pooled = sum(w * e for w, e, _ in effects) / w_sum
    sgn = _sign(pooled)
    if sgn == 0:
        return 0.5
    agree = sum(w for w, e, _ in effects if _sign(e) == sgn)
    return agree / w_sum


def pool_and_grade(cards: Iterable[dict], cfg: BankingConfig) -> dict:
    effects = []
    refs = set()
    for c in cards:
        ecs = _card_to_effects(c, cfg)
        effects.extend(ecs)
        for _, __, pid in ecs:
            refs.add(pid)
    W = sum(w for w, _, __ in effects)
    if W <= 0 or len(effects) < 2:
        return {"pooled_effect": 0.0, "consistency": 0.0, "weight": W, "grade": "D", "top_refs": []}
    E = sum(w * e for w, e, __ in effects) / W
    S = _consistency(effects)

    # Confidence proxy from weight & consistency
    confidence = min(1.0, 0.35 + 0.4 * (W / (cfg.w_min + 1e-9)) + 0.25 * S)

    # Grade rules
    grade = "D"
    if W < cfg.w_min or len(effects) < 2:
        grade = "D"
    else:
        absE = abs(E)
        if absE < cfg.null_eps and S >= 0.6:
            grade = "F"
        elif E <= -cfg.negative_thresh and S >= 0.6:
            grade = "F"
        elif absE >= cfg.effect_a and confidence >= 0.7:
            grade = "A"
        elif absE >= cfg.effect_b and confidence >= 0.5:
            grade = "B"
        elif (absE >= cfg.effect_small and absE < 0.15) or (absE >= 0.15 and S < 0.6):
            grade = "C"
        else:
            # If it's near zero and inconsistent, D (inconclusive)
            grade = "D"

    return {
        "pooled_effect": E,
        "consistency": S,
        "weight": W,
        "confidence": confidence,
        "grade": grade,
        "top_refs": list(refs)[:10],
    }


def load_cards_for(supplement: str, goal: Optional[str], cards_dir: Path) -> List[dict]:
    out = []
    for p in cards_dir.glob("*.json"):
        try:
            card = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = card.get("meta") or {}
        supps = [str(s).lower() for s in (meta.get("supplements") or [])]
        if str(supplement).lower() not in supps:
            continue
        if goal:
            if (meta.get("primary_goal") or "").lower() != goal.lower():
                # also allow outcomes domain match
                domains = [str(o.get("domain") or "").lower() for o in card.get("outcomes") or []]
                if goal.lower() not in domains:
                    continue
        out.append(card)
    return out


