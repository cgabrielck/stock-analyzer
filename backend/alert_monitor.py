from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


DEFAULT_REARM_PCT = 0.005


def evaluate_alert_transition(
    rule: Dict[str, Any], previous_price: Optional[float], current_price: float,
    *, armed: bool = True,
) -> Dict[str, Any]:
    if current_price <= 0:
        return {"triggered": False, "armed": armed, "reason": "invalid_price"}
    event_type = rule.get("event_type")
    data = rule.get("rule_data", {})
    comparison = data.get("comparison")
    if event_type == "entry_zone" or comparison == "enters_range":
        low, high = float(data["low"]), float(data["high"])
        inside = low <= current_price <= high
        was_inside = previous_price is not None and low <= previous_price <= high
        triggered = armed and inside and not was_inside
        rearmed = armed or not inside
    else:
        level = float(data["price"])
        buffer = level * DEFAULT_REARM_PCT
        if comparison == "crosses_up":
            triggered = armed and previous_price is not None and previous_price < level <= current_price
            rearmed = armed or current_price < level - buffer
        elif comparison == "crosses_down":
            triggered = armed and previous_price is not None and previous_price > level >= current_price
            rearmed = armed or current_price > level + buffer
        elif comparison == "at_or_above":
            triggered = armed and current_price >= level and (previous_price is None or previous_price < level)
            rearmed = armed or current_price < level - buffer
        elif comparison == "at_or_below":
            triggered = armed and current_price <= level and (previous_price is None or previous_price > level)
            rearmed = armed or current_price > level + buffer
        else:
            return {"triggered": False, "armed": armed, "reason": "unsupported_comparison"}
    return {"triggered": triggered, "armed": False if triggered else rearmed, "reason": "triggered" if triggered else "no_transition"}


def quote_is_fresh(quote: Dict[str, Any], now: Optional[datetime] = None, max_age_minutes: int = 20) -> bool:
    if quote.get("stale") or not quote.get("quote_time"):
        return False
    current = now or datetime.now(timezone.utc)
    try:
        timestamp = datetime.fromisoformat(str(quote["quote_time"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age = current - timestamp.astimezone(timezone.utc)
    return timedelta(minutes=-2) <= age <= timedelta(minutes=max_age_minutes)


def event_idempotency_key(rule_id: str, quote_time: str, current_price: float) -> str:
    return f"{rule_id}:{quote_time}:{current_price:.6f}"
