from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from agents.alpha_vantage_data import fetch_daily_adjusted


CHART_INTERVALS: Dict[str, Tuple[str, str]] = {
    "1m": ("1m", "5d"),
    "5m": ("5m", "1mo"),
    "15m": ("15m", "1mo"),
    "30m": ("30m", "1mo"),
    "60m": ("60m", "2mo"),
    "1d": ("1d", "1y"),
}
REQUIRED_OHLCV = ("Open", "High", "Low", "Close", "Volume")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_chart_data(ticker: str, interval: str, extended_hours: bool) -> Dict[str, Any]:
    yf_interval, period = CHART_INTERVALS.get(interval, CHART_INTERVALS["1d"])
    is_intraday = yf_interval != "1d"
    errors = []
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(
            period=period,
            interval=yf_interval,
            prepost=extended_hours if is_intraday else False,
            auto_adjust=False,
        )
        frame = normalize_chart_frame(history, is_intraday, extended_hours)
        if len(frame) >= 10:
            return {
                "data": frame,
                "provider": "yfinance",
                "interval": yf_interval,
                "period": period,
                "extended_hours": extended_hours,
            }
        errors.append("yfinance returned insufficient history")
    except Exception as exc:
        errors.append(f"yfinance: {type(exc).__name__}: {exc}")

    if not is_intraday:
        alpha_history = fetch_daily_adjusted(ticker, period=period)
        if alpha_history:
            frame = normalize_chart_frame(alpha_history["data"], False, False)
            if len(frame) >= 10:
                return {
                    "data": frame,
                    "provider": "alpha_vantage",
                    "interval": "1d",
                    "period": period,
                    "extended_hours": False,
                    "adjusted": True,
                    "as_of": alpha_history.get("as_of"),
                }
        errors.append("Alpha Vantage returned insufficient daily history")

    try:
        history = _fetch_yahoo_chart_http(ticker, yf_interval, period, extended_hours and is_intraday)
        frame = normalize_chart_frame(history, is_intraday, extended_hours)
        if len(frame) >= 10:
            return {
                "data": frame,
                "provider": "yahoo_chart_http",
                "interval": yf_interval,
                "period": period,
                "extended_hours": extended_hours,
            }
        errors.append("Yahoo chart endpoint returned insufficient history")
    except Exception as exc:
        errors.append(f"Yahoo chart endpoint: {type(exc).__name__}: {exc}")

    return {
        "error": " | ".join(errors),
        "stage": "history",
        "provider": "unavailable",
        "interval": yf_interval,
        "period": period,
    }


def normalize_chart_frame(history: Any, is_intraday: bool, extended_hours: bool) -> pd.DataFrame:
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=REQUIRED_OHLCV)
    if not set(REQUIRED_OHLCV).issubset(history.columns):
        return pd.DataFrame(columns=REQUIRED_OHLCV)
    frame = history.loc[:, REQUIRED_OHLCV].copy()
    for column in REQUIRED_OHLCV:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[(frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce", utc=True))
    valid = ~index.isna()
    frame = frame.loc[valid]
    index = index[valid].tz_convert("America/New_York")
    frame.index = index
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if is_intraday and not extended_hours:
        frame = frame.between_time("09:30", "15:59", inclusive="both")
    return frame


def _fetch_yahoo_chart_http(ticker: str, interval: str, period: str, prepost: bool) -> pd.DataFrame:
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"interval": interval, "range": period, "includePrePost": str(prepost).lower(), "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json().get("chart", {})
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    results = payload.get("result") or []
    if not results:
        return pd.DataFrame()
    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not timestamps or not quotes:
        return pd.DataFrame()
    length = min(len(timestamps), *(len(quotes.get(key.lower()) or []) for key in REQUIRED_OHLCV))
    index = pd.to_datetime(timestamps[:length], unit="s", utc=True)
    return pd.DataFrame(
        {column: (quotes.get(column.lower()) or [])[:length] for column in REQUIRED_OHLCV},
        index=index,
    )
