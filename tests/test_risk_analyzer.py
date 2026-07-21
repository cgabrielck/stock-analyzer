import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.risk_analyzer import calculate_risk_metrics, risk_label


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
