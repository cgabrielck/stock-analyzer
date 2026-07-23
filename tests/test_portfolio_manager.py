import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pandas as pd

from agents import portfolio_manager
from agents.portfolio_manager import (
    MAX_KELLY_FRACTION,
    calculate_portfolio_weights,
    compute_correlations,
    normalize_capped_weights,
    build_portfolio,
)


def test_normalized_weights_respect_position_cap() -> None:
    weights = normalize_capped_weights({"A": 0.25, "B": 0.01, "C": 0.01})

    assert all(weight <= MAX_KELLY_FRACTION for weight in weights.values())
    assert round(sum(weights.values()), 4) == 0.75


def test_normalized_weights_reach_target_when_capacity_exists() -> None:
    weights = normalize_capped_weights({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2})

    assert round(sum(weights.values()), 4) == 0.9
    assert all(weight <= MAX_KELLY_FRACTION for weight in weights.values())


def test_portfolio_weights_use_equal_allocation_without_calibration() -> None:
    recommendations = [
        {"ticker": ticker, "total_score": score, "price": 100}
        for ticker, score in zip("ABCDE", [90, 80, 70, 60, 50])
    ]

    weights, method = calculate_portfolio_weights(recommendations, calibration={})

    assert method == "equal"
    assert set(weights.values()) == {0.18}


def test_portfolio_weights_use_ready_calibration() -> None:
    calibration = {
        "model_version": 2,
        "ready": True,
        "observations": 100,
        "min_observations": 100,
        "global_win_rate": 0.55,
        "bin_width": 10,
        "prior_strength": 20,
        "bins": {
            "80-90": {"wins": 16, "count": 20},
            "60-70": {"wins": 8, "count": 20},
        },
    }
    recommendations = [
        {"ticker": "A", "total_score": 85, "price": 100},
        {"ticker": "B", "total_score": 65, "price": 100},
        {"ticker": "C", "total_score": 65, "price": 100},
        {"ticker": "D", "total_score": 65, "price": 100},
        {"ticker": "E", "total_score": 65, "price": 100},
    ]

    weights, method = calculate_portfolio_weights(recommendations, calibration=calibration)

    assert method == "calibrated_kelly"
    assert weights["A"] > weights["B"]


def test_negative_correlation_is_not_flagged_as_concentration(monkeypatch) -> None:
    prices = pd.DataFrame({
        "A": [100.0, 110.0, 99.0, 108.9],
        "B": [100.0, 90.0, 99.0, 89.1],
    })
    monkeypatch.setattr(portfolio_manager.yf, "download", lambda *args, **kwargs: prices)

    _, high_pairs, close = compute_correlations(["A", "B"])

    assert high_pairs == []
    assert list(close.columns) == ["A", "B"]


def test_positive_correlation_is_flagged(monkeypatch) -> None:
    prices = pd.DataFrame({
        "A": [100.0, 110.0, 99.0, 108.9],
        "B": [200.0, 220.0, 198.0, 217.8],
    })
    monkeypatch.setattr(portfolio_manager.yf, "download", lambda *args, **kwargs: prices)

    _, high_pairs, _ = compute_correlations(["A", "B"])

    assert high_pairs == [("A", "B", 1.0)]


def test_portfolio_uses_supplied_session_state_and_includes_cash(monkeypatch) -> None:
    monkeypatch.setattr(portfolio_manager, "compute_correlations", lambda tickers: (None, [], pd.DataFrame()))
    monkeypatch.setattr(portfolio_manager, "load_calibration_snapshot", lambda: {})
    recommendations = [{"ticker": "A", "total_score": 80, "price": 100, "risk_metrics": {"available": True}}]

    first = build_portfolio(recommendations, total_capital=1000, target_allocation=0.5, previous_state={}, journal=[])
    second = build_portfolio(recommendations, total_capital=1000, target_allocation=0.5, previous_state={}, journal=[])

    assert first["portfolio_value"] == 1000
    assert len(first["journal"]) == 1
    assert len(second["journal"]) == 1
    assert first["session_state"] is not second["session_state"]
