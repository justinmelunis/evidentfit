from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


@dataclass
class RuleActions:
    grade_delta: Optional[int] = None
    dose_multiplier: Optional[float] = None
    note: Optional[str] = None


@dataclass
class Level3Rule:
    id: str
    applies_to: List[str]
    profile: Dict[str, Any]
    severity: str  # "hard_stop" | "caution"
    actions: RuleActions


def _load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml") and yaml is not None:
        return yaml.safe_load(text)
    return json.loads(text)


def _coerce_rule(obj: Dict[str, Any]) -> Level3Rule:
    rid = str(obj["id"]) if "id" in obj else None
    if not rid:
        raise ValueError("rule missing id")
    applies_to = obj.get("applies_to") or ["*"]
    if not isinstance(applies_to, list):
        raise ValueError(f"rule {rid} applies_to must be list")
    severity = str(obj.get("severity") or "caution").lower()
    if severity not in ("hard_stop", "caution"):
        raise ValueError(f"rule {rid} invalid severity: {severity}")
    profile = obj.get("profile") or {}
    if not isinstance(profile, dict):
        raise ValueError(f"rule {rid} profile must be object")
    actions_raw = obj.get("actions") or {}
    if not isinstance(actions_raw, dict):
        raise ValueError(f"rule {rid} actions must be object")
    actions = RuleActions(
        grade_delta=actions_raw.get("grade_delta"),
        dose_multiplier=actions_raw.get("dose_multiplier"),
        note=actions_raw.get("note"),
    )
    return Level3Rule(id=rid, applies_to=applies_to, profile=profile, severity=severity, actions=actions)


def load_rules(paths: List[Path]) -> List[Level3Rule]:
    rules: List[Level3Rule] = []
    for p in paths:
        if not p.exists():
            continue
        data = _load_file(p)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    rules.append(_coerce_rule(item))
        elif isinstance(data, dict):
            # single object or container {rules:[...]}
            if "rules" in data and isinstance(data["rules"], list):
                for item in data["rules"]:
                    if isinstance(item, dict):
                        rules.append(_coerce_rule(item))
            else:
                rules.append(_coerce_rule(data))
    # de-duplicate by id keeping first
    seen = set()
    unique: List[Level3Rule] = []
    for r in rules:
        if r.id in seen:
            continue
        seen.add(r.id)
        unique.append(r)
    return unique


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_rules(rules: List[Level3Rule], index_version: str, version_prefix: str = "l3") -> Dict[str, Any]:
    payload = {
        "version": f"{version_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "index_version": index_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rules": [
            {
                "id": r.id,
                "applies_to": r.applies_to,
                "profile": r.profile,
                "severity": r.severity,
                "actions": {k: v for k, v in asdict(r.actions).items() if v is not None},
            }
            for r in rules
        ],
    }
    payload["sha256"] = _sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def save_compiled(payload: Dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    return out_path


