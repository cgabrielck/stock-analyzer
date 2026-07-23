from datetime import datetime, timezone
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from accounts.models import SavedPlanVersion
from saved_plan_outcomes import evaluate_saved_plan_outcome


def _plan(stance="bullish") -> SavedPlanVersion:
    bearish = stance == "bearish"
    return SavedPlanVersion(
        plan_id="plan-1", ticker="TEST", version=1, analysis_timestamp="2026-01-02T20:00:00+00:00",
        plan_data={
            "decision": {"stance": stance},
            "alert_levels": {
                "entry_zone": {"low": 99, "high": 101, "comparison": "enters_range"},
                "confirmation": {"price": 98 if bearish else 102, "comparison": "crosses_down" if bearish else "crosses_up"},
                "stop": {"price": 105 if bearish else 95, "comparison": "at_or_above" if bearish else "at_or_below", "watch_only": stance == "neutral"},
                "targets": [
                    {"price": 93 if bearish else 107, "comparison": "at_or_below" if bearish else "at_or_above", "watch_only": stance == "neutral"},
                    {"price": 87 if bearish else 113, "comparison": "at_or_below" if bearish else "at_or_above", "watch_only": stance == "neutral"},
                ],
            },
        },
    )


def _history(periods=8, bearish=False):
    index = pd.date_range("2026-01-02", periods=periods, freq="B")
    closes = [100, 101, 103, 106, 108, 110, 111, 112]
    if bearish:
        closes = [100, 99, 97, 95, 92, 90, 89, 88]
    values = closes[:periods]
    return pd.DataFrame({
        "Open": values, "High": [value + 2 for value in values],
        "Low": [value - 2 for value in values], "Close": values,
        "Stock Splits": 0.0,
    }, index=index)


def test_bullish_five_day_outcome_uses_post_analysis_open_and_exact_spy_dates() -> None:
    stock = _history()
    spy = _history()

    result = evaluate_saved_plan_outcome(
        _plan(), stock, spy, 5, evaluated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["status"] == "complete"
    assert result["anchor_date"] == "2026-01-05"
    assert result["endpoint_date"] == "2026-01-09"
    assert result["reference_price"] == 101
    assert result["endpoint_price"] == 110
    assert result["raw_alpha_pct"] == 0
    assert result["directional_return_pct"] > 0
    assert result["level_events"]["confirmation"]["hit"] is True


def test_bearish_outcome_reverses_directional_return() -> None:
    result = evaluate_saved_plan_outcome(
        _plan("bearish"), _history(bearish=True), _history(), 5,
        evaluated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["raw_return_pct"] < 0
    assert result["directional_return_pct"] > 0
    assert result["mfe_pct"] > 0


def test_outcome_remains_pending_without_enough_complete_sessions() -> None:
    result = evaluate_saved_plan_outcome(
        _plan(), _history(periods=4), _history(periods=4), 5,
        evaluated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["status"] == "pending"
    assert result["remaining_bars"] == 2
