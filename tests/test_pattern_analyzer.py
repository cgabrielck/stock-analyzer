import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.pattern_analyzer import analyze_patterns
from pine_export import build_pine_script


def _frame(closes):
    index = pd.date_range("2025-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame({"Open": closes, "High": [value + 1 for value in closes], "Low": [value - 1 for value in closes], "Close": closes, "Volume": 100}, index=index)


def test_double_bottom_requires_neckline_confirmation() -> None:
    data = _frame([110, 109, 108, 107, 100, 99, 98, 97, 98, 100, 103, 105, 104, 102, 100, 98, 97.5, 98, 100, 103, 106, 107, 108, 109])
    result = analyze_patterns(data, atr=2)

    assert result["patterns"]
    pattern = result["patterns"][0]
    assert pattern["kind"] == "double_bottom"
    assert pattern["status"] == "confirmed"
    assert pattern["target"] > pattern["neckline"]


def test_analysis_uses_only_bars_provided() -> None:
    data = _frame([110, 109, 108, 107, 100, 99, 98, 97, 98, 100, 103, 105, 104, 102, 100, 98, 97.5, 98, 100, 103, 104, 104, 104])
    result = analyze_patterns(data, atr=2)

    assert result["patterns"][0]["status"] == "watching"


def test_pine_export_contains_trade_risk_levels() -> None:
    script = build_pine_script("aapl", {"entry_zone": {"low": 100, "high": 102}, "confirmation_price": 103, "stop_loss": 98, "targets": [106, 110]})

    assert "//@version=6" in script
    assert "AlphaDesk Research - AAPL" in script
    assert "Stop" in script
