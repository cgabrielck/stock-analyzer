import concurrent.futures
import math
from typing import Any, Dict, Optional

import yfinance as yf
import pandas as pd
import numpy as np

from utils.cache import cache
from utils.price_utils import get_latest_quote
from agents.risk_analyzer import calculate_risk_metrics, risk_label
from agents.auto_upgrader import agent_state


def _compute_rsi(series: pd.Series, length: int = 14) -> float:
    if len(series) < length + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None


def _compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    if len(series) < slow + signal:
        return None, None, None
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return (
        float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None,
        float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else None,
        float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else None,
    )


def _compute_sma(series: pd.Series, length: int) -> float:
    if len(series) < length:
        return None
    s = series.rolling(length).mean()
    return float(s.iloc[-1]) if not pd.isna(s.iloc[-1]) else None


def _compute_bb(series: pd.Series, length: int = 20, std: int = 2):
    if len(series) < length:
        return None, None
    sma = series.rolling(length).mean()
    stddev = series.rolling(length).std()
    upper = sma + stddev * std
    lower = sma - stddev * std
    return (
        float(upper.iloc[-1]) if not pd.isna(upper.iloc[-1]) else None,
        float(lower.iloc[-1]) if not pd.isna(lower.iloc[-1]) else None,
    )


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> float:
    if len(close) < length + 1:
        return None
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(length).mean()
    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None


def calculate_technical_score(data: Dict[str, Any]) -> float:
    """Score live technical data using the same rules as the walk-forward backtest."""
    rsi = data.get("rsi_14")
    macd_hist = data.get("macd_histogram")
    sma20 = data.get("sma_20")
    sma50 = data.get("sma_50")
    price = data.get("price")
    volume_ratio = data.get("volume_ratio_10_50")
    bb_upper = data.get("bb_upper")
    bb_lower = data.get("bb_lower")
    total = 0

    if sma20 and sma50 and sma20 > sma50:
        total += 25
    elif sma20 and sma50 and sma20 < sma50:
        total += 5
    if rsi is not None:
        if 40 <= rsi <= 60:
            total += 20
        elif 30 <= rsi < 40:
            total += 15
        elif rsi < 30:
            total += 10
        elif rsi > 70:
            total += 5
    if macd_hist is not None:
        total += 15 if macd_hist > 0 else 5
    if volume_ratio is not None:
        total += 10 if volume_ratio > 0.8 else 5 if volume_ratio < 0.5 else 0
    if price and sma50 and sma50 > 0:
        price_vs_sma50 = (price / sma50 - 1) * 100
        if -5 <= price_vs_sma50 <= 5:
            total += 10
        elif price_vs_sma50 > 5:
            total += 5
        elif price_vs_sma50 < -15:
            total -= 5
    if bb_lower and bb_upper and price:
        if price <= bb_lower:
            total += 15
        elif price >= bb_upper:
            total += 5
    return round(max(0, min(100, total)), 1)


def compute_technical_indicators(
    ticker: str, period: str = "6mo", force_refresh: bool = False,
) -> Dict[str, Any]:
    if not force_refresh:
        cached = cache.get(f"tech_{ticker}", "info")
        if cached:
            return cached

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist is None or hist.empty or len(hist) < 50:
            return {"ticker": ticker, "error": "insufficient_history"}

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]

        last_close = float(close.iloc[-1])
        latest_quote = get_latest_quote(stock, fallback_close=last_close)
        current_price = latest_quote["price"]
        price_session = latest_quote["session"]
        rsi_val = _compute_rsi(close, 14)
        macd_line, macd_signal, macd_hist = _compute_macd(close)
        bb_upper, bb_lower = _compute_bb(close)
        sma20_val = _compute_sma(close, 20)
        sma50_val = _compute_sma(close, 50)
        atr_val = _compute_atr(high, low, close)

        vol_short = float(volume.tail(10).mean())
        vol_long = float(volume.tail(50).mean())
        volume_ratio = vol_short / vol_long if vol_long > 0 else None

        price_vs_sma50 = ((current_price / sma50_val) - 1) * 100 if sma50_val and sma50_val > 0 else None

        result: Dict[str, Any] = {
            "ticker": ticker,
            "price": current_price,
            "price_session": price_session,
            "price_source": latest_quote["source"],
            "price_quote_time": latest_quote["quote_time"],
            "price_market_state": latest_quote["market_state"],
            "price_stale": latest_quote["stale"],
            "rsi_14": rsi_val,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "sma_20": sma20_val,
            "sma_50": sma50_val,
            "atr_14": atr_val,
            "volume_ratio_10_50": volume_ratio,
            "price_vs_sma50_pct": price_vs_sma50,
        }
        risk_metrics = calculate_risk_metrics(close)
        risk_metrics["risk_level"] = risk_label(risk_metrics)
        result["risk_metrics"] = risk_metrics

        _enrich_interpretation(result)
        result["technical_score"] = calculate_technical_score(result)

        agent_state.log_source_result(f"technical:{ticker}", True)
        cache.set(f"tech_{ticker}", "info", result)
        return result

    except Exception as e:
        agent_state.log_source_result(f"technical:{ticker}", False, str(e))
        return {"ticker": ticker, "error": str(e)}


def _enrich_interpretation(data: Dict[str, Any]) -> None:
    rsi = data.get("rsi_14")
    if rsi is not None:
        if rsi >= 70:
            data["rsi_signal"] = "overbought"
        elif rsi <= 30:
            data["rsi_signal"] = "oversold"
        else:
            data["rsi_signal"] = "neutral"

    macd = data.get("macd_histogram")
    if macd is not None:
        data["macd_signal"] = "bullish" if macd > 0 else "bearish"

    bb_upper = data.get("bb_upper")
    bb_lower = data.get("bb_lower")
    price = data.get("price")
    if price is not None and bb_upper is not None and bb_lower is not None:
        if price >= bb_upper:
            data["bb_signal"] = "above_upper"
        elif price <= bb_lower:
            data["bb_signal"] = "below_lower"
        else:
            data["bb_signal"] = "within"

    sma50 = data.get("sma_50")
    if price is not None and sma50 is not None and sma50 > 0:
        data["trend_signal"] = "uptrend" if price > sma50 else "downtrend"

    vol_ratio = data.get("volume_ratio_10_50")
    if vol_ratio is not None:
        data["volume_signal"] = "high" if vol_ratio > 1.5 else ("low" if vol_ratio < 0.5 else "normal")


def compute_all_technical(
    tickers: list[str],
    force_refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            executor.submit(compute_technical_indicators, t, "6mo", force_refresh): t
            for t in tickers
        }
        for future in concurrent.futures.as_completed(future_map):
            ticker = future_map[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                results[ticker] = {"ticker": ticker, "error": str(e)}
    return results
