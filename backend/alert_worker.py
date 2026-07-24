import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

import yfinance as yf

from accounts.repository import SupabaseAccountRepository
from alert_monitor import evaluate_alert_transition, event_idempotency_key, quote_is_fresh
from config import get_account_settings
from utils.price_utils import get_latest_quote


LOGGER = logging.getLogger(__name__)


def check_alerts(repository: SupabaseAccountRepository) -> Dict[str, int]:
    rules = repository.list_enabled_alerts()
    quotes: Dict[str, Dict[str, Any]] = {}
    result = {"rules": len(rules), "evaluated": 0, "triggered": 0, "stale": 0}
    for rule in rules:
        ticker = rule.get("ticker")
        if not ticker:
            continue
        if ticker not in quotes:
            quotes[ticker] = get_latest_quote(yf.Ticker(ticker))
        quote = quotes[ticker]
        if not quote_is_fresh(quote):
            result["stale"] += 1
            continue
        price = float(quote["price"])
        transition = evaluate_alert_transition(
            rule, float(rule["last_price"]) if rule.get("last_price") is not None else None,
            price, armed=bool(rule.get("armed", True)),
        )
        quote_time = _iso_quote_time(quote["quote_time"])
        repository.record_alert_evaluation(
            rule["id"], price, quote_time, transition["armed"], transition["triggered"],
            event_idempotency_key(rule["id"], quote_time, price),
            {"source": quote.get("source"), "session": quote.get("session")},
        )
        result["evaluated"] += 1
        result["triggered"] += int(transition["triggered"])
    return result


def run_forever(interval_seconds: int = 60) -> None:
    settings = get_account_settings()
    if not settings.configured:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    repository = SupabaseAccountRepository(settings.supabase_url, settings.supabase_service_role_key)
    while True:
        started = time.monotonic()
        try:
            LOGGER.info("Alert check completed: %s", check_alerts(repository))
        except Exception:
            LOGGER.exception("Alert check failed")
        time.sleep(max(1, interval_seconds - int(time.monotonic() - started)))


def _iso_quote_time(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, (int, float)):
        timestamp = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_forever(int(os.getenv("ALERT_INTERVAL_SECONDS", "60")))
