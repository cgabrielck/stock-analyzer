import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from utils import chart_utils


def _history() -> pd.DataFrame:
    index = pd.DatetimeIndex([
        pd.Timestamp("2026-07-21 08:00", tz="America/New_York"),
        pd.Timestamp("2026-07-21 09:30", tz="America/New_York"),
        pd.Timestamp("2026-07-21 10:00", tz="America/New_York"),
        pd.Timestamp("2026-07-21 16:30", tz="America/New_York"),
    ])
    return pd.DataFrame({
        "Open": [99, 100, 101, 102], "High": [100, 102, 103, 104],
        "Low": [98, 99, 100, 101], "Close": [99.5, 101, 102, 103],
        "Volume": [10, 20, 30, 40],
    }, index=index)


def test_normalize_chart_frame_filters_extended_hours() -> None:
    frame = chart_utils.normalize_chart_frame(_history(), is_intraday=True, extended_hours=False)

    assert len(frame) == 2
    assert str(frame.index.tz) == "America/New_York"
    assert frame.index[0].strftime("%H:%M") == "09:30"


def test_normalize_chart_frame_keeps_extended_hours() -> None:
    frame = chart_utils.normalize_chart_frame(_history(), is_intraday=True, extended_hours=True)

    assert len(frame) == 4


def test_fetch_chart_data_falls_back_to_http(monkeypatch) -> None:
    class EmptyTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **kwargs):
            return pd.DataFrame()

    repeated = pd.concat([_history()] * 3).sort_index()
    repeated.index = pd.date_range("2026-07-21 09:30", periods=len(repeated), freq="5min", tz="America/New_York")
    monkeypatch.setattr(chart_utils.yf, "Ticker", EmptyTicker)
    monkeypatch.setattr(chart_utils, "_fetch_yahoo_chart_http", lambda *args, **kwargs: repeated)
    chart_utils.fetch_chart_data.clear()

    result = chart_utils.fetch_chart_data("AAPL", "5m", False)

    assert result["provider"] == "yahoo_chart_http"
    assert len(result["data"]) == 12


def test_invalid_ohlcv_returns_empty_frame() -> None:
    frame = chart_utils.normalize_chart_frame(pd.DataFrame({"Close": [100]}), False, False)

    assert frame.empty
