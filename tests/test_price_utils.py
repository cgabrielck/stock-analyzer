from datetime import datetime, timezone
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from utils.price_utils import _session_from_timestamp, get_latest_quote


NOW = datetime(2026, 7, 21, 13, 15, tzinfo=timezone.utc)


class FakeStock:
    def __init__(self, info, history=None):
        self.info = info
        self._history = history if history is not None else pd.DataFrame()
        self.history_calls = []

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        return self._history


def test_pre_market_state_selects_pre_market_price() -> None:
    stock = FakeStock({
        "marketState": "PRE",
        "preMarketPrice": 105,
        "preMarketTime": NOW.timestamp(),
        "regularMarketPrice": 100,
        "regularMarketTime": (NOW.replace(hour=0)).timestamp(),
        "postMarketPrice": 99,
    })

    quote = get_latest_quote(stock, now=NOW)

    assert quote["price"] == 105
    assert quote["session"] == "Pre-Market Trading"
    assert quote["source"] == "yahoo_pre_market"
    assert quote["stale"] is False


def test_regular_state_ignores_retained_extended_prices() -> None:
    stock = FakeStock({
        "marketState": "REGULAR",
        "preMarketPrice": 105,
        "postMarketPrice": 99,
        "regularMarketPrice": 110,
        "regularMarketTime": NOW.timestamp(),
    })

    assert get_latest_quote(stock, now=NOW)["price"] == 110


def test_post_state_selects_after_hours_price() -> None:
    stock = FakeStock({
        "marketState": "POST",
        "preMarketPrice": 105,
        "regularMarketPrice": 110,
        "postMarketPrice": 112,
        "postMarketTime": NOW.timestamp(),
    })

    quote = get_latest_quote(stock, now=NOW)

    assert quote["price"] == 112
    assert quote["session"] == "After-Hours Trading"


def test_stale_pre_market_uses_fresh_intraday_extended_bar() -> None:
    index = pd.DatetimeIndex([NOW - pd.Timedelta(minutes=2)])
    history = pd.DataFrame({"Close": [107.0]}, index=index)
    stock = FakeStock({
        "marketState": "PRE",
        "preMarketPrice": 105,
        "preMarketTime": (NOW - pd.Timedelta(hours=2)).timestamp(),
        "regularMarketPrice": 100,
    }, history)

    quote = get_latest_quote(stock, now=NOW)

    assert quote["price"] == 107
    assert quote["source"] == "yahoo_1m_extended_hours"
    assert stock.history_calls == [{"period": "5d", "interval": "1m", "prepost": True, "auto_adjust": False}]


def test_closed_market_labels_latest_quote_as_closed() -> None:
    stock = FakeStock({
        "marketState": "CLOSED",
        "regularMarketPrice": 100,
        "regularMarketTime": (NOW - pd.Timedelta(hours=10)).timestamp(),
        "postMarketPrice": 102,
        "postMarketTime": (NOW - pd.Timedelta(hours=8)).timestamp(),
    })

    quote = get_latest_quote(stock, now=NOW)

    assert quote["price"] == 102
    assert quote["session"] == "Market Closed"
    assert quote["stale"] is True


def test_0900_new_york_is_pre_market() -> None:
    timestamp = pd.Timestamp("2026-07-21 09:00", tz="America/New_York").to_pydatetime()

    assert _session_from_timestamp(timestamp) == "Pre-Market Trading"
