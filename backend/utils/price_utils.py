from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import yfinance as yf


SESSION_LABELS = {
    "PRE": "Pre-Market Trading",
    "PREPRE": "Overnight Trading",
    "REGULAR": "Regular Trading Hours",
    "POST": "After-Hours Trading",
    "POSTPOST": "After-Hours Trading",
    "CLOSED": "Market Closed",
}

SESSION_ORDER = ("overnight", "pre_market", "regular", "after_hours")
SESSION_NAMES = {
    "overnight": "Overnight Trading",
    "pre_market": "Pre-Market Trading",
    "regular": "Regular Trading Hours",
    "after_hours": "After-Hours Trading",
}


def get_latest_quote(
    stock: yf.Ticker,
    fallback_close: Optional[float] = None,
    info: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return the price for Yahoo's active market session with provenance metadata."""
    current_time = now or datetime.now(timezone.utc)
    try:
        quote_info = info if info is not None else stock.info
    except Exception:
        quote_info = {}

    state = str(quote_info.get("marketState") or "").upper()
    candidates = {
        "PRE": _candidate(quote_info, "preMarketPrice", "preMarketTime", "yahoo_pre_market"),
        "REGULAR": _candidate(quote_info, "regularMarketPrice", "regularMarketTime", "yahoo_regular_market"),
        "POST": _candidate(quote_info, "postMarketPrice", "postMarketTime", "yahoo_after_hours"),
    }
    if candidates["REGULAR"] is None:
        candidates["REGULAR"] = _candidate(quote_info, "currentPrice", "regularMarketTime", "yahoo_current_price")

    expected = "PRE" if state in {"PRE", "PREPRE"} else "POST" if state in {"POST", "POSTPOST"} else "REGULAR"
    selected = candidates.get(expected)
    active_state = state in {"PRE", "PREPRE", "REGULAR", "POST", "POSTPOST"}
    if active_state and selected and _is_current_candidate(selected, current_time, quote_info, state):
        return _quote_result(selected, SESSION_LABELS.get(state, SESSION_LABELS[expected]), state, stale=False)

    intraday = _latest_intraday_quote(stock, current_time)
    if intraday and (not selected or _candidate_time(intraday) >= _candidate_time(selected)):
        return _quote_result(intraday, _session_from_timestamp(intraday["time"]), state, stale=False)

    if active_state and selected:
        return _quote_result(selected, SESSION_LABELS.get(state, SESSION_LABELS[expected]), state, stale=True)

    available = [candidate for candidate in candidates.values() if candidate]
    if available:
        newest = max(available, key=_candidate_time)
        session = SESSION_LABELS.get(state, "Market Closed")
        return _quote_result(newest, session, state or "UNKNOWN", stale=state not in {"PRE", "PREPRE", "REGULAR", "POST", "POSTPOST"})

    if _valid_price(fallback_close):
        return {
            "price": float(fallback_close),
            "session": SESSION_LABELS.get(state, "Regular Trading Hours"),
            "source": "history_close_fallback",
            "quote_time": None,
            "market_state": state or "UNKNOWN",
            "stale": True,
        }
    return {
        "price": None,
        "session": SESSION_LABELS.get(state, "Unknown Session"),
        "source": "unavailable",
        "quote_time": None,
        "market_state": state or "UNKNOWN",
        "stale": True,
    }


def get_latest_price(
    stock: yf.Ticker,
    fallback_close: Optional[float] = None,
    info: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], str]:
    quote = get_latest_quote(stock, fallback_close=fallback_close, info=info)
    return quote["price"], quote["session"]


def get_session_ranges(stock: yf.Ticker) -> Dict[str, Any]:
    """Return the latest observed OHLC range for each US trading session."""
    result: Dict[str, Any] = {
        "source": "yahoo_1m_extended_hours",
        "timezone": "America/New_York",
        "provider_note": "Overnight coverage depends on Yahoo availability.",
        "sessions": {key: {"name": SESSION_NAMES[key], "available": False} for key in SESSION_ORDER},
    }
    try:
        history = stock.history(period="5d", interval="1m", prepost=True, auto_adjust=False)
        if history is None or history.empty:
            return result
        required = {"High", "Low", "Close"}
        if not required.issubset(history.columns):
            return result
        frame = history.copy()
        index = pd.DatetimeIndex(frame.index)
        index = index.tz_localize("UTC") if index.tz is None else index
        eastern = index.tz_convert("America/New_York")
        frame["_timestamp"] = eastern
        frame["_session"] = [_session_key(ts.hour * 60 + ts.minute) for ts in eastern]
        frame["_session_date"] = [
            (ts + timedelta(days=1)).date().isoformat() if key == "overnight" and ts.hour >= 20
            else ts.date().isoformat()
            for ts, key in zip(eastern, frame["_session"])
        ]
        for key in SESSION_ORDER:
            subset = frame[frame["_session"] == key]
            if subset.empty:
                continue
            latest_date = subset["_session_date"].max()
            subset = subset[subset["_session_date"] == latest_date]
            highs = pd.to_numeric(subset["High"], errors="coerce").dropna()
            lows = pd.to_numeric(subset["Low"], errors="coerce").dropna()
            closes = pd.to_numeric(subset["Close"], errors="coerce").dropna()
            if highs.empty or lows.empty or closes.empty:
                continue
            result["sessions"][key] = {
                "name": SESSION_NAMES[key],
                "available": True,
                "date": latest_date,
                "high": round(float(highs.max()), 4),
                "low": round(float(lows.min()), 4),
                "last": round(float(closes.iloc[-1]), 4),
                "start_time": subset["_timestamp"].iloc[0].isoformat(),
                "end_time": subset["_timestamp"].iloc[-1].isoformat(),
                "bars": int(len(subset)),
            }
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _candidate(info: Dict[str, Any], price_key: str, time_key: str, source: str) -> Optional[Dict[str, Any]]:
    price = info.get(price_key)
    if not _valid_price(price):
        return None
    return {"price": float(price), "time": _parse_timestamp(info.get(time_key)), "source": source}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, pd.Timestamp):
        timestamp = value.to_pydatetime()
        return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        parsed = pd.to_datetime(value, utc=True)
        return parsed.to_pydatetime() if not pd.isna(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _is_current_candidate(candidate: Dict[str, Any], now: datetime, info: Dict[str, Any], state: str) -> bool:
    quote_time = candidate.get("time")
    if quote_time is None:
        return False
    delay_minutes = float(info.get("exchangeDataDelayedBy") or 0)
    allowed_age_seconds = max(900.0, delay_minutes * 60 + 300.0)
    age_seconds = (now - quote_time).total_seconds()
    return -120 <= age_seconds <= allowed_age_seconds


def _latest_intraday_quote(stock: yf.Ticker, now: datetime) -> Optional[Dict[str, Any]]:
    try:
        history = stock.history(period="5d", interval="1m", prepost=True, auto_adjust=False)
        if history is None or history.empty or "Close" not in history:
            return None
        closes = pd.to_numeric(history["Close"], errors="coerce")
        closes = closes[closes.map(_valid_price)]
        if closes.empty:
            return None
        timestamp = closes.index[-1]
        quote_time = _parse_timestamp(timestamp)
        if quote_time is None or (now - quote_time).total_seconds() > 900:
            return None
        return {"price": float(closes.iloc[-1]), "time": quote_time, "source": "yahoo_1m_extended_hours"}
    except Exception:
        return None


def _session_from_timestamp(value: Optional[datetime]) -> str:
    if value is None:
        return "Unknown Session"
    eastern = pd.Timestamp(value).tz_convert("America/New_York")
    minutes = eastern.hour * 60 + eastern.minute
    if minutes < 4 * 60:
        return "Overnight Trading"
    if minutes < 9 * 60 + 30:
        return "Pre-Market Trading"
    if minutes < 16 * 60:
        return "Regular Trading Hours"
    if minutes < 20 * 60:
        return "After-Hours Trading"
    return "Overnight Trading"


def _session_key(minutes: int) -> str:
    if minutes < 4 * 60 or minutes >= 20 * 60:
        return "overnight"
    if minutes < 9 * 60 + 30:
        return "pre_market"
    if minutes < 16 * 60:
        return "regular"
    return "after_hours"


def _quote_result(candidate: Dict[str, Any], session: str, state: str, stale: bool) -> Dict[str, Any]:
    quote_time = candidate.get("time")
    return {
        "price": candidate["price"],
        "session": session,
        "source": candidate["source"],
        "quote_time": quote_time.isoformat() if quote_time else None,
        "market_state": state or "UNKNOWN",
        "stale": stale,
    }


def _candidate_time(candidate: Dict[str, Any]) -> datetime:
    return candidate.get("time") or datetime.min.replace(tzinfo=timezone.utc)


def _valid_price(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError):
        return False
