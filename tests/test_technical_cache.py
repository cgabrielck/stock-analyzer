import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import technical_analyzer


def test_technical_cache_is_separated_by_period(monkeypatch) -> None:
    calls = []
    index = pd.date_range("2025-01-01", periods=220, freq="B")
    history = pd.DataFrame({
        "Open": range(100, 320), "High": range(101, 321), "Low": range(99, 319),
        "Close": range(100, 320), "Volume": [1000] * 220,
    }, index=index)

    class FakeTicker:
        info = {"marketState": "CLOSED", "regularMarketPrice": 319}

        def history(self, period, **kwargs):
            calls.append(period)
            return history

    monkeypatch.setattr(technical_analyzer.yf, "Ticker", lambda ticker: FakeTicker())
    monkeypatch.setattr(technical_analyzer.agent_state, "log_source_result", lambda *args, **kwargs: None)
    technical_analyzer.cache.delete("tech_v3_TEST_6mo", "info")
    technical_analyzer.cache.delete("tech_v3_TEST_1y", "info")

    technical_analyzer.compute_technical_indicators("TEST", period="6mo")
    technical_analyzer.compute_technical_indicators("TEST", period="1y")
    cached = technical_analyzer.compute_technical_indicators("TEST", period="1y")

    assert [period for period in calls if period in {"6mo", "1y"}] == ["6mo", "1y"]
    assert cached["technical_from_cache"] is True
    assert cached["technical_period"] == "1y"


def test_technical_rejects_quote_history_scale_mismatch(monkeypatch) -> None:
    index = pd.date_range("2025-01-01", periods=220, freq="B")
    history = pd.DataFrame({
        "Open": [980.0] * 220, "High": [990.0] * 220, "Low": [970.0] * 220,
        "Close": [980.0] * 220, "Volume": [1000] * 220,
    }, index=index)

    class FakeTicker:
        info = {"marketState": "CLOSED", "regularMarketPrice": 98.0, "regularMarketTime": 1780000000}

        def history(self, **kwargs):
            return history

    monkeypatch.setattr(technical_analyzer.yf, "Ticker", lambda ticker: FakeTicker())

    result = technical_analyzer.compute_technical_indicators("SCALE_TEST", period="1y", force_refresh=True)

    assert result["error"] == "price_scale_mismatch"
    assert result["quote_to_history_ratio"] == 0.1
