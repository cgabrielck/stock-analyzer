import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.risk_analyzer import (
    calculate_portfolio_risk, calculate_risk_adjusted_score, calculate_risk_metrics, risk_label,
)


def test_calculate_risk_metrics_on_sufficient_price_history() -> None:
    index = pd.date_range("2025-01-01", periods=100, freq="B")
    returns = pd.Series(np.where(np.arange(100) % 2 == 0, 0.01, -0.005), index=index)
    prices = 100 * (1 + returns).cumprod()
    benchmark = 100 * (1 + returns * 0.5).cumprod()

    metrics = calculate_risk_metrics(prices, benchmark)

    assert metrics["available"] is True
    assert metrics["observations"] == 99
    assert metrics["annual_volatility_pct"] > 0
    assert metrics["var_95_daily_pct"] < 0
    assert metrics["max_drawdown_pct"] < 0
    assert metrics["beta"] is not None


def test_risk_metrics_reject_short_history() -> None:
    prices = pd.Series([100, 101, 102])

    metrics = calculate_risk_metrics(prices)

    assert metrics == {"available": False, "observations": 2, "reason": "insufficient_history"}


def test_risk_label_marks_volatile_stock_high_risk() -> None:
    assert risk_label({"available": True, "annual_volatility_pct": 50, "max_drawdown_pct": -20, "beta": 1}) == "high"


def test_risk_adjusted_score_penalty_boundaries() -> None:
    low = calculate_risk_adjusted_score(80, {"available": True, "annual_volatility_pct": 24.9, "max_drawdown_pct": -24.9})
    medium = calculate_risk_adjusted_score(80, {"available": True, "annual_volatility_pct": 25, "max_drawdown_pct": -10})
    high = calculate_risk_adjusted_score(80, {"available": True, "annual_volatility_pct": 45, "max_drawdown_pct": -50})

    assert low["risk_adjusted_score"] == 80
    assert medium["risk_adjusted_score"] == 75
    assert high["risk_adjusted_score"] == 70
    assert high["risk_penalty"] == 10


def test_missing_risk_is_neutral_and_score_is_clamped() -> None:
    assert calculate_risk_adjusted_score(120, {"available": False}) == {
        "risk_adjusted_score": 100.0,
        "risk_penalty": 0.0,
        "risk_penalty_level": "unknown",
    }


def test_risk_metrics_use_fixed_latest_window() -> None:
    base = pd.Series(np.linspace(50, 100, 126))
    prefixed = pd.concat([pd.Series([1000.0, 10.0]), base], ignore_index=True)

    assert calculate_risk_metrics(base) == calculate_risk_metrics(prefixed)


def test_portfolio_risk_uses_market_values_and_preserves_cash() -> None:
    index = pd.date_range("2025-01-01", periods=81, freq="B")
    returns = pd.DataFrame({
        "A": np.where(np.arange(81) % 2 == 0, 0.01, -0.004),
        "B": np.where(np.arange(81) % 3 == 0, 0.006, -0.002),
    }, index=index)
    prices = 100 * (1 + returns).cumprod()

    result = calculate_portfolio_risk(prices, {"A": 600, "B": 200}, cash=200)

    expected_returns = prices.pct_change(fill_method=None).dropna()
    weights = np.array([0.6, 0.2])
    expected_volatility = np.sqrt(weights @ expected_returns.cov().to_numpy() @ weights) * np.sqrt(252) * 100
    assert result["available"] is True
    assert result["cash_weight_pct"] == 20.0
    assert result["actual_weights"] == {"A": 0.6, "B": 0.2}
    assert result["annual_volatility_pct"] == round(expected_volatility, 2)
    assert result["stress_tests"][1]["portfolio_change_pct"] == -16.0


def test_portfolio_risk_reports_partial_coverage_without_renormalizing() -> None:
    index = pd.date_range("2025-01-01", periods=81, freq="B")
    prices = pd.DataFrame({"A": np.linspace(100, 120, 81)}, index=index)

    result = calculate_portfolio_risk(prices, {"A": 600, "B": 200}, cash=200)

    assert result["available"] is True
    assert result["coverage_status"] == "partial"
    assert result["actual_weights"]["A"] == 0.6
    assert result["equity_coverage_pct"] == 75.0
    assert result["excluded_tickers"]["B"] == "price_unavailable"
