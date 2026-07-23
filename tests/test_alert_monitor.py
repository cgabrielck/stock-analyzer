from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from alert_monitor import evaluate_alert_transition, event_idempotency_key, quote_is_fresh


def test_bullish_confirmation_requires_upward_crossing() -> None:
    rule = {"event_type": "confirmation", "rule_data": {"price": 100, "comparison": "crosses_up"}}
    assert evaluate_alert_transition(rule, 99, 101)["triggered"] is True
    assert evaluate_alert_transition(rule, 101, 102)["triggered"] is False


def test_bearish_confirmation_requires_downward_crossing() -> None:
    rule = {"event_type": "confirmation", "rule_data": {"price": 100, "comparison": "crosses_down"}}
    assert evaluate_alert_transition(rule, 101, 99)["triggered"] is True
    assert evaluate_alert_transition(rule, 99, 98)["triggered"] is False


def test_entry_zone_triggers_only_when_entering_range() -> None:
    rule = {"event_type": "entry_zone", "rule_data": {"low": 95, "high": 100, "comparison": "enters_range"}}
    assert evaluate_alert_transition(rule, 102, 99)["triggered"] is True
    assert evaluate_alert_transition(rule, 98, 97)["triggered"] is False


def test_stale_quote_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    assert quote_is_fresh({"quote_time": (now - timedelta(minutes=5)).isoformat(), "stale": False}, now)
    assert not quote_is_fresh({"quote_time": (now - timedelta(hours=1)).isoformat(), "stale": False}, now)
    assert not quote_is_fresh({"quote_time": now.isoformat(), "stale": True}, now)
    assert not quote_is_fresh({"quote_time": "invalid", "stale": False}, now)
    assert not quote_is_fresh({"quote_time": (now + timedelta(minutes=5)).isoformat(), "stale": False}, now)


def test_event_idempotency_key_is_deterministic() -> None:
    assert event_idempotency_key("rule", "2026-01-01T00:00:00Z", 100) == event_idempotency_key("rule", "2026-01-01T00:00:00Z", 100)
