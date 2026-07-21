import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.portfolio_manager import MAX_KELLY_FRACTION, normalize_capped_weights


def test_normalized_weights_respect_position_cap() -> None:
    weights = normalize_capped_weights({"A": 0.25, "B": 0.01, "C": 0.01})

    assert all(weight <= MAX_KELLY_FRACTION for weight in weights.values())
    assert round(sum(weights.values()), 4) == 0.75


def test_normalized_weights_reach_target_when_capacity_exists() -> None:
    weights = normalize_capped_weights({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2})

    assert round(sum(weights.values()), 4) == 0.9
    assert all(weight <= MAX_KELLY_FRACTION for weight in weights.values())
