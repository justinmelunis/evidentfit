from pathlib import Path
from evidentfit_shared.banking.aggregate import BankingConfig, pool_and_grade


def test_pool_and_grade_simple():
    cfg = BankingConfig.load(Path("config/banking.yml"))
    # Two small positive outcomes with decent n → should not be D
    cards = [
        {
            "meta": {"study_type": "randomized_controlled_trial", "pmid": "1"},
            "population": {"n": 60},
            "outcomes": [{"direction": "increase", "effect_size_norm": 0.30}],
        },
        {
            "meta": {"study_type": "randomized_controlled_trial", "pmid": "2"},
            "population": {"n": 80},
            "outcomes": [{"direction": "increase", "effect_size_norm": 0.28}],
        },
    ]
    agg = pool_and_grade(cards, cfg)
    assert agg["weight"] > 0
    assert agg["pooled_effect"] > 0
    assert agg["grade"] in ("B", "A", "C")  # depending on exact thresholds


