from pathlib import Path
import json
from evidentfit_shared.banking.adjust import load_rules, apply_suitability


def test_suitability_rules():
    rules = load_rules(Path("config/suitability_rules.json"))
    out = apply_suitability(
        supplement="creatine",
        intrinsic_grade="A",
        rules=rules,
        user_profile={"pregnant": True},
    )
    assert out["final_grade"] == "F"
    assert "Avoid" in out["suitability"]

    out2 = apply_suitability(
        supplement="caffeine",
        intrinsic_grade="B",
        rules=rules,
        user_profile={"conditions": ["Anxiety_Disorder"]},
    )
    assert out2["final_grade"] == "C"
    assert "Caution" in out2["suitability"]


