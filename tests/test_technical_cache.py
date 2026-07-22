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

        def history(self, period):
            calls.append(period)
            return history

    monkeypatch.setattr(technical_analyzer.yf, "Ticker", lambda ticker: FakeTicker())
    monkeypatch.setattr(technical_analyzer.agent_state, "log_source_result", lambda *args, **kwargs: None)
    technical_analyzer.cache.delete("tech_v2_TEST_6mo", "info")
    technical_analyzer.cache.delete("tech_v2_TEST_1y", "info")

    technical_analyzer.compute_technical_indicators("TEST", period="6mo")
    technical_analyzer.compute_technical_indicators("TEST", period="1y")
    cached = technical_analyzer.compute_technical_indicators("TEST", period="1y")

    assert calls == ["6mo", "1y"]
    assert cached["technical_from_cache"] is True
    assert cached["technical_period"] == "1y"
