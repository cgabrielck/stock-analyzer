import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

from utils.cache import cache


load_dotenv()

BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 15
FUNDAMENTAL_TTL = 86400
PRICE_TTL = 21600
_throttle_lock = threading.Lock()
_throttled_until = 0.0


class AlphaVantageError(RuntimeError):
    pass


class AlphaVantageRateLimitError(AlphaVantageError):
    pass


def get_api_key() -> Optional[str]:
    value = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if value:
        return value
    try:
        import streamlit as st

        value = str(st.secrets.get("ALPHA_VANTAGE_API_KEY", "")).strip()
        return value or None
    except Exception:
        return None


def is_configured() -> bool:
    return bool(get_api_key())


def fetch_fundamentals(ticker: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    if not is_configured():
        return None
    payloads: Dict[str, Dict[str, Any]] = {}
    for function in ("OVERVIEW", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW", "EARNINGS"):
        try:
            payloads[function] = _request(function, ticker, FUNDAMENTAL_TTL, force_refresh)
        except AlphaVantageRateLimitError:
            break
        except AlphaVantageError:
            continue
    if not payloads.get("OVERVIEW") and not any(payloads.get(name) for name in payloads):
        return None
    return normalize_fundamentals(ticker, payloads)


def fetch_daily_adjusted(
    ticker: str,
    *,
    period: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    if not is_configured():
        return None
    try:
        payload = _request(
            "TIME_SERIES_DAILY_ADJUSTED", ticker, PRICE_TTL, force_refresh,
            extra={"outputsize": "full"},
        )
    except AlphaVantageError:
        return None
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict) or not series:
        return None
    frame = normalize_daily_adjusted(series)
    if frame.empty:
        return None
    if start:
        frame = frame[frame.index >= pd.Timestamp(start)]
    if end:
        frame = frame[frame.index < pd.Timestamp(end)]
    if period and not start:
        offsets = {"1mo": 1, "2mo": 2, "3mo": 3, "6mo": 6, "1y": 12, "2y": 24, "5y": 60}
        months = offsets.get(period)
        if months:
            frame = frame[frame.index >= frame.index.max() - pd.DateOffset(months=months)]
    if frame.empty:
        return None
    return {
        "data": frame,
        "provider": "alpha_vantage",
        "endpoint": "TIME_SERIES_DAILY_ADJUSTED",
        "adjusted": True,
        "price_basis": "latest_raw_close",
        "adjustment_factor": frame.attrs.get("latest_adjustment_factor"),
        "as_of": frame.index[-1].date().isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_global_quote(ticker: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    if not is_configured():
        return None
    try:
        payload = _request("GLOBAL_QUOTE", ticker, 300, force_refresh)
    except AlphaVantageError:
        return None
    quote = payload.get("Global Quote") or {}
    price = _number(quote.get("05. price"))
    latest_day = quote.get("07. latest trading day")
    if price is None:
        return None
    return {
        "price": price,
        "price_session": "Market Closed",
        "price_source": "alpha_vantage_global_quote",
        "price_quote_time": latest_day,
        "price_market_state": "UNKNOWN",
        "price_stale": True,
    }


def normalize_fundamentals(ticker: str, payloads: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    overview = payloads.get("OVERVIEW") or {}
    result: Dict[str, Any] = {
        "ticker": ticker,
        "longName": overview.get("Name") or None,
        "sector": overview.get("Sector") or None,
        "industry": overview.get("Industry") or None,
        "market_cap": _number(overview.get("MarketCapitalization")),
        "pe_ratio": _number(overview.get("PERatio")),
        "forward_pe": _number(overview.get("ForwardPE")),
        "peg": _number(overview.get("PEGRatio")),
        "ps_ratio": _number(overview.get("PriceToSalesRatioTTM")),
        "pb_ratio": _number(overview.get("PriceToBookRatio")),
        "ev_ebitda": _number(overview.get("EVToEBITDA")),
        "dividend_yield": _number(overview.get("DividendYield")),
        "beta": _number(overview.get("Beta")),
        "fifty_two_week_high": _number(overview.get("52WeekHigh")),
        "fifty_two_week_low": _number(overview.get("52WeekLow")),
        "target_mean_price": _number(overview.get("AnalystTargetPrice")),
        "profit_margin": _percent(overview.get("ProfitMargin")),
        "roe": _percent(overview.get("ReturnOnEquityTTM")),
        "revenue_growth": _percent(overview.get("QuarterlyRevenueGrowthYOY")),
        "eps_growth": _percent(overview.get("QuarterlyEarningsGrowthYOY")),
        "revenue_ttm": _number(overview.get("RevenueTTM")),
        "eps": _number(overview.get("EPS")),
    }
    report_dates = []
    income_reports = _reports(payloads.get("INCOME_STATEMENT"))
    if income_reports:
        current, previous = income_reports[0], income_reports[1] if len(income_reports) > 1 else {}
        report_dates.append(current.get("fiscalDateEnding"))
        revenue = _number(current.get("totalRevenue"))
        previous_revenue = _number(previous.get("totalRevenue"))
        net_income = _number(current.get("netIncome"))
        previous_income = _number(previous.get("netIncome"))
        result["revenue_ttm"] = result.get("revenue_ttm") or revenue
        result["net_income"] = net_income
        result["revenue_growth"] = result.get("revenue_growth") if result.get("revenue_growth") is not None else _growth(revenue, previous_revenue)
        result["net_income_growth"] = _growth(net_income, previous_income)
        if result.get("profit_margin") is None and revenue and net_income is not None:
            result["profit_margin"] = net_income / revenue * 100
    balance_reports = _reports(payloads.get("BALANCE_SHEET"))
    if balance_reports:
        current = balance_reports[0]
        report_dates.append(current.get("fiscalDateEnding"))
        debt = _number(current.get("totalDebt"))
        if debt is None:
            short_debt = _number(current.get("shortTermDebt"))
            long_debt = _number(current.get("longTermDebt")) or _number(current.get("longTermDebtNoncurrent"))
            debt = (short_debt or 0) + (long_debt or 0)
            if short_debt is None and long_debt is None:
                debt = _number(current.get("shortLongTermDebtTotal"))
        equity = _number(current.get("totalShareholderEquity"))
        if equity and debt is not None:
            result["debt_equity"] = debt / equity
    cash_reports = _reports(payloads.get("CASH_FLOW"))
    if cash_reports:
        current = cash_reports[0]
        report_dates.append(current.get("fiscalDateEnding"))
        operating = _number(current.get("operatingCashflow"))
        capex = _number(current.get("capitalExpenditures"))
        if operating is not None and capex is not None:
            result["fcf"] = operating - abs(capex)
    earnings = payloads.get("EARNINGS") or {}
    annual_earnings = earnings.get("annualEarnings") or []
    if annual_earnings:
        current = annual_earnings[0]
        previous = annual_earnings[1] if len(annual_earnings) > 1 else {}
        report_dates.append(current.get("fiscalDateEnding"))
        current_eps = _number(current.get("reportedEPS"))
        result["eps"] = result.get("eps") if result.get("eps") is not None else current_eps
        if result.get("eps_growth") is None:
            result["eps_growth"] = _growth(current_eps, _number(previous.get("reportedEPS")))
    result = {key: value for key, value in result.items() if value is not None}
    valid_dates = [value for value in report_dates if value]
    result["_alpha_meta"] = {
        "as_of": max(valid_dates) if valid_dates else overview.get("LatestQuarter"),
        "endpoints": [name for name, payload in payloads.items() if payload],
    }
    return result


def normalize_daily_adjusted(series: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for day, values in series.items():
        close = _number(values.get("4. close"))
        adjusted_close = _number(values.get("5. adjusted close"))
        rows.append({
            "Date": day,
            "Open": _number(values.get("1. open")),
            "High": _number(values.get("2. high")),
            "Low": _number(values.get("3. low")),
            "RawClose": close,
            "AdjustedClose": adjusted_close or close,
            "Volume": _number(values.get("6. volume")) or 0,
        })
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    frame = pd.DataFrame(rows).set_index("Date")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce"))
    frame = frame[~frame.index.isna()]
    frame = frame.apply(pd.to_numeric, errors="coerce").dropna(subset=["Open", "High", "Low", "RawClose", "AdjustedClose"])
    frame = frame[(frame["RawClose"] > 0) & (frame["AdjustedClose"] > 0)].sort_index()
    raw_factors = frame["AdjustedClose"] / frame["RawClose"]
    latest_factor = float(raw_factors.iloc[-1])
    normalized_factors = raw_factors / latest_factor
    for column in ("Open", "High", "Low", "RawClose"):
        frame[column] = frame[column] * normalized_factors
    frame["Volume"] = frame["Volume"] / normalized_factors
    frame["Close"] = frame["RawClose"]
    frame = frame.drop(columns=["RawClose", "AdjustedClose"])
    frame = frame[(frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame.attrs["latest_adjustment_factor"] = latest_factor
    frame.attrs["price_basis"] = "latest_raw_close"
    return frame


def _request(
    function: str,
    ticker: str,
    ttl: int,
    force_refresh: bool,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    global _throttled_until
    key = f"av_v1_{function}_{ticker}_{(extra or {}).get('outputsize', '')}"
    if not force_refresh:
        cached = cache.get(key, "financials", ttl=ttl)
        if cached:
            return cached
    with _throttle_lock:
        if time.monotonic() < _throttled_until:
            raise AlphaVantageRateLimitError("Alpha Vantage is temporarily rate limited")
    api_key = get_api_key()
    if not api_key:
        raise AlphaVantageError("Alpha Vantage is not configured")
    params = {"function": function, "symbol": ticker, "apikey": api_key, **(extra or {})}
    try:
        response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise AlphaVantageError(f"Alpha Vantage request failed: {type(exc).__name__}") from exc
    message = payload.get("Note") or payload.get("Information")
    if message:
        with _throttle_lock:
            _throttled_until = time.monotonic() + 60
        raise AlphaVantageRateLimitError("Alpha Vantage request limit reached")
    if payload.get("Error Message"):
        raise AlphaVantageError("Alpha Vantage rejected the symbol")
    cache.set(key, "financials", payload, ttl=ttl)
    return payload


def _reports(payload: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if not payload:
        return []
    reports = payload.get("annualReports") or payload.get("quarterlyReports") or []
    return sorted(reports, key=lambda item: item.get("fiscalDateEnding", ""), reverse=True)


def _number(value: Any) -> Optional[float]:
    if value is None or str(value).strip().lower() in {"", "none", "null", "-", "nan"}:
        return None
    try:
        number = float(str(value).replace(",", ""))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> Optional[float]:
    number = _number(value)
    return number * 100 if number is not None else None


def _growth(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1) * 100
