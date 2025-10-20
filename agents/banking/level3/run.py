import os
from pathlib import Path
from typing import List

from evidentfit_shared.suitability.rules import load_rules, compile_rules, save_compiled
from evidentfit_shared.utils import read_index_version


def main():
    base_dir = Path("config")
    candidates: List[Path] = []
    # default locations
    candidates.append(base_dir / "suitability_rules.json")
    rules_dir = base_dir / "rules"
    if rules_dir.exists():
        for p in rules_dir.glob("*.yml"):
            candidates.append(p)
        for p in rules_dir.glob("*.yaml"):
            candidates.append(p)
        for p in rules_dir.glob("*.json"):
            candidates.append(p)

    rules = load_rules(candidates)
    if not rules:
        print("No Level 3 rules found; ensure config/suitability_rules.json or config/rules/* exists.")
        return

    try:
        index_version = read_index_version()
    except Exception:
        index_version = os.getenv("INDEX_VERSION", "v1")

    compiled = compile_rules(rules, index_version=index_version)
    out = save_compiled(compiled, base_dir / "compiled_rules.json")
    # Avoid Unicode arrows for Windows consoles
    print(f"Compiled {len(rules)} rules -> {out}")


if __name__ == "__main__":
    main()


