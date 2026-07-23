import json
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional


PLAN_SCHEMA_VERSION = 1
ALERT_EVENT_TYPES = ("entry_zone", "confirmation", "stop", "target_1", "target_2")


def build_saved_plan(
    ticker: str, result: Dict[str, Any], analysis_timestamp: str, language: str,
) -> Dict[str, Any]:
    trade = result.get("trade_plan", {})
    if not is_saveable_plan(result):
        raise ValueError("plan_not_saveable")
    technical = result.get("technical", {})
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "ticker": ticker.strip().upper(),
        "analysis_timestamp": analysis_timestamp,
        "analysis_language": language,
        "decision": {key: trade.get(key) for key in (
            "stance", "action", "position_side", "stop_type", "setup",
        )},
        "levels": {key: trade.get(key) for key in (
            "entry_zone", "confirmation_price", "stop_loss", "targets", "risk_reward",
            "entry_reference", "risk_per_share", "atr_14",
        )},
        "execution": {key: trade.get(key) for key in ("execution_window", "method")},
        "scores": {
            "short_term": result.get("short_term", {}),
            "long_term": result.get("long_term", {}),
            "quant_score": result.get("quant_score"),
            "risk_adjusted_score": result.get("risk_adjusted_score"),
            "technical_score": technical.get("technical_score"),
            "risk_level": technical.get("risk_metrics", {}).get("risk_level", "unknown"),
        },
        "avoid": result.get("avoid", {}),
        "decision_basis": trade.get("decision_basis", {}),
        "market_snapshot": {key: technical.get(key) for key in (
            "price", "price_session", "price_source", "price_quote_time", "price_market_state",
            "price_stale", "ema_21", "sma_50", "bb_lower", "bb_upper",
        )},
        "provenance": result.get("provenance", {}),
        "alert_levels": build_alert_levels(trade),
    }
    normalized = _json_value(payload)
    json.dumps(normalized, allow_nan=False)
    return normalized


def is_saveable_plan(result: Dict[str, Any]) -> bool:
    if result.get("error"):
        return False
    trade = result.get("trade_plan", {})
    entry = trade.get("entry_zone", {})
    targets = trade.get("targets", [])
    required = [entry.get("low"), entry.get("high"), trade.get("confirmation_price"), trade.get("stop_loss")]
    return (
        not trade.get("error")
        and trade.get("stance") in {"bullish", "bearish", "neutral"}
        and trade.get("action") != "no_trade"
        and len(targets) >= 2
        and all(_finite(value) for value in [*required, targets[0], targets[1]])
    )


def build_alert_levels(trade: Dict[str, Any]) -> Dict[str, Any]:
    stance = trade.get("stance")
    confirmation = "crosses_down" if stance == "bearish" else "crosses_up"
    adverse = "at_or_above" if stance == "bearish" else "at_or_below"
    favorable = "at_or_below" if stance == "bearish" else "at_or_above"
    targets = trade.get("targets", [])
    risk_reward = trade.get("risk_reward", [])
    return {
        "entry_zone": {**trade.get("entry_zone", {}), "comparison": "enters_range"},
        "confirmation": {"price": trade.get("confirmation_price"), "comparison": confirmation},
        "stop": {
            "price": trade.get("stop_loss"), "comparison": adverse,
            "kind": trade.get("stop_type"), "watch_only": stance == "neutral",
        },
        "targets": [
            {
                "price": price, "comparison": favorable,
                "risk_reward": risk_reward[index] if index < len(risk_reward) else None,
                "watch_only": stance == "neutral",
            }
            for index, price in enumerate(targets[:2])
        ],
    }


def alert_rule_data(plan_data: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    if event_type not in ALERT_EVENT_TYPES:
        raise ValueError("invalid_alert_event")
    levels = plan_data["alert_levels"]
    if event_type == "entry_zone":
        return levels["entry_zone"]
    if event_type == "confirmation":
        return levels["confirmation"]
    if event_type == "stop":
        return levels["stop"]
    return levels["targets"][int(event_type[-1]) - 1]


def plan_changes(previous: Dict[str, Any], current: Dict[str, Any]) -> List[Dict[str, Any]]:
    paths = {
        "stance": ("decision", "stance"),
        "action": ("decision", "action"),
        "entry_low": ("levels", "entry_zone", "low"),
        "entry_high": ("levels", "entry_zone", "high"),
        "confirmation": ("levels", "confirmation_price"),
        "stop": ("levels", "stop_loss"),
        "target_1": ("levels", "targets", 0),
        "target_2": ("levels", "targets", 1),
    }
    changes = []
    for label, path in paths.items():
        old, new = _get(previous, path), _get(current, path)
        if old != new:
            changes.append({"field": label, "previous": old, "current": new})
    return changes


def _get(data: Any, path: tuple) -> Any:
    value = data
    for key in path:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError):
            return None
    return value


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported plan value: {type(value).__name__}")
