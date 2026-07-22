import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backtesting.our_picks import (
    _benchmark_return,
    _confidence_level,
    simulate_trade_path,
    summarize_validation,
)


def _future(rows):
    return pd.DataFrame(rows, index=pd.date_range("2026-01-02", periods=len(rows), freq="B"))


def _bullish_plan():
    return {"entry_zone": {"low": 99, "high": 101}, "stop_loss": 95, "targets": [107, 113]}


def test_bullish_path_uses_next_day_and_deducts_round_trip_costs() -> None:
    future = _future([
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1},
        {"Open": 101, "High": 114, "Low": 100, "Close": 113, "Volume": 1},
    ])

    result = simulate_trade_path(future, _bullish_plan(), "bullish", 15, 5)

    assert result["entry_date"] == "2026-01-02"
    assert result["exit_date"] == "2026-01-05"
    assert result["holding_bars"] == 2
    assert result["holding_calendar_days"] == 3
    assert result["entry_execution_type"] == "open_in_entry_zone"
    assert result["exit_execution_type"] == "target_limit"
    assert result["round_trip_cost_bps"] == 40
    assert result["exit_reason"] == "target2"
    assert result["net_return_pct"] == round((113 / 100 - 1) * 100 - 0.4, 2)


def test_ambiguous_daily_bar_uses_stop_first() -> None:
    future = _future([
        {"Open": 100, "High": 114, "Low": 94, "Close": 105, "Volume": 1},
    ])

    result = simulate_trade_path(future, _bullish_plan(), "bullish", 0, 0)

    assert result["ambiguous_bar"] is True
    assert result["exit_reason"] == "stop"
    assert result["exit_price"] == 95


def test_gap_through_stop_uses_open_after_entry_day() -> None:
    future = _future([
        {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1},
        {"Open": 90, "High": 92, "Low": 88, "Close": 91, "Volume": 1},
    ])

    result = simulate_trade_path(future, _bullish_plan(), "bullish", 0, 0)

    assert result["exit_reason"] == "stop"
    assert result["exit_price"] == 90


def test_bearish_return_has_directional_sign() -> None:
    plan = {"entry_zone": {"low": 99, "high": 101}, "stop_loss": 105, "targets": [93, 87]}
    future = _future([
        {"Open": 100, "High": 101, "Low": 98, "Close": 99, "Volume": 1},
        {"Open": 99, "High": 100, "Low": 86, "Close": 87, "Volume": 1},
    ])

    result = simulate_trade_path(future, plan, "bearish", 0, 0)

    assert result["exit_reason"] == "target2"
    assert result["net_return_pct"] == 13.0


def test_unfilled_and_neutral_do_not_create_wins() -> None:
    unfilled = _future([{"Open": 110, "High": 112, "Low": 108, "Close": 111, "Volume": 1}])
    neutral = _future([{"Open": 100, "High": 103, "Low": 99, "Close": 102, "Volume": 1}])

    assert simulate_trade_path(unfilled, _bullish_plan(), "bullish")["entered"] is False
    assert simulate_trade_path(neutral, _bullish_plan(), "neutral")["exit_reason"] == "watch_only"


def test_confidence_requires_minimum_sample_size() -> None:
    samples = [{
        "entered": True, "stance": "bullish", "net_return_pct": 2.0,
        "excess_return_pct": 1.0, "target1_hit": True, "target2_hit": False,
        "stop_hit": False, "mae_pct": -1.0,
    } for _ in range(11)]

    result = summarize_validation("TEST", samples, 20)

    assert result["confidence"]["level"] == "insufficient"
    assert result["sample_count"] == 11


def test_confidence_cannot_be_medium_without_positive_excess_return() -> None:
    samples = [{"net_return_pct": 2.0, "excess_return_pct": -0.5} for _ in range(24)]

    confidence = _confidence_level(samples)

    assert confidence["level"] == "low"


def test_benchmark_uses_exact_entry_and_exit_close_dates() -> None:
    benchmark = pd.DataFrame(
        {"Close": [100, 150, 110]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )

    result = _benchmark_return(benchmark, "2026-01-02", "2026-01-06")

    assert result == pytest.approx(0.1)


def test_benchmark_returns_none_when_exact_date_is_missing() -> None:
    benchmark = pd.DataFrame(
        {"Close": [100, 110]},
        index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
    )

    assert _benchmark_return(benchmark, "2026-01-03", "2026-01-06") is None
