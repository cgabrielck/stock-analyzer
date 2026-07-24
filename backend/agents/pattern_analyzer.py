"""Completed price-pattern annotations for research charts, not price forecasts."""

from typing import Any, Dict, List, Optional

import pandas as pd


PIVOT_WINDOW = 4
MIN_PATTERN_BARS = 16


def analyze_patterns(frame: pd.DataFrame, atr: Optional[float] = None) -> Dict[str, Any]:
    """Analyze only bars supplied in *frame*; callers can safely truncate it in backtests."""
    if frame is None or len(frame) < MIN_PATTERN_BARS:
        return {"patterns": [], "fibonacci": None, "method": "insufficient_history"}
    data = frame.dropna(subset=["High", "Low", "Close"])
    pivots = _confirmed_pivots(data)
    patterns = _double_patterns(data, pivots, atr)
    return {
        "patterns": patterns,
        "fibonacci": _fibonacci(data, pivots),
        "method": "confirmed_pivots",
        "pivot_window": PIVOT_WINDOW,
    }


def _confirmed_pivots(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    pivots: List[Dict[str, Any]] = []
    # A pivot is emitted only after PIVOT_WINDOW later bars confirm it.
    for index in range(PIVOT_WINDOW, len(frame) - PIVOT_WINDOW):
        window = frame.iloc[index - PIVOT_WINDOW:index + PIVOT_WINDOW + 1]
        high, low = float(frame["High"].iloc[index]), float(frame["Low"].iloc[index])
        if high >= float(window["High"].max()):
            pivots.append({"kind": "high", "index": index, "time": frame.index[index], "price": high})
        if low <= float(window["Low"].min()):
            pivots.append({"kind": "low", "index": index, "time": frame.index[index], "price": low})
    return _alternating_pivots(pivots)


def _alternating_pivots(pivots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for pivot in pivots:
        if not result or result[-1]["kind"] != pivot["kind"]:
            result.append(pivot)
            continue
        previous = result[-1]
        if (pivot["kind"] == "high" and pivot["price"] >= previous["price"]) or (
            pivot["kind"] == "low" and pivot["price"] <= previous["price"]
        ):
            result[-1] = pivot
    return result


def _double_patterns(frame: pd.DataFrame, pivots: List[Dict[str, Any]], atr: Optional[float]) -> List[Dict[str, Any]]:
    if len(pivots) < 3:
        return []
    tolerance = 0.025
    close = float(frame["Close"].iloc[-1])
    for first, middle, second in reversed(list(zip(pivots, pivots[1:], pivots[2:]))):
        if first["kind"] == second["kind"] == "low" and middle["kind"] == "high":
            equal = abs(first["price"] - second["price"]) / max(first["price"], second["price"]) <= tolerance
            if equal:
                neckline = middle["price"]
                base = (first["price"] + second["price"]) / 2
                return [_pattern("double_bottom", first, middle, second, close, neckline, neckline + (neckline - base), min(first["price"], second["price"]) - _buffer(atr, base), "up")]
        if first["kind"] == second["kind"] == "high" and middle["kind"] == "low":
            equal = abs(first["price"] - second["price"]) / max(first["price"], second["price"]) <= tolerance
            if equal:
                neckline = middle["price"]
                peak = (first["price"] + second["price"]) / 2
                return [_pattern("double_top", first, middle, second, close, neckline, max(0.01, neckline - (peak - neckline)), max(first["price"], second["price"]) + _buffer(atr, peak), "down")]
    return []


def _pattern(kind: str, first: Dict[str, Any], middle: Dict[str, Any], second: Dict[str, Any], close: float, neckline: float, target: float, invalidation: float, direction: str) -> Dict[str, Any]:
    confirmed = close >= neckline if direction == "up" else close <= neckline
    return {
        "kind": kind,
        "status": "confirmed" if confirmed else "watching",
        "direction": direction,
        "anchors": [first, middle, second],
        "neckline": round(neckline, 4),
        "target": round(target, 4),
        "invalidation": round(invalidation, 4),
    }


def _buffer(atr: Optional[float], price: float) -> float:
    return max(float(atr or 0) * 0.25, price * 0.005)


def _fibonacci(frame: pd.DataFrame, pivots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(pivots) < 2:
        return None
    start, end = pivots[-2:]
    if start["kind"] == end["kind"] or start["price"] == end["price"]:
        return None
    low, high = sorted((float(start["price"]), float(end["price"])))
    difference = high - low
    direction = "up" if end["price"] > start["price"] else "down"
    ratios = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
    levels = {
        str(ratio): round(high - difference * ratio if direction == "up" else low + difference * ratio, 4)
        for ratio in ratios
    }
    return {"direction": direction, "start": start, "end": end, "levels": levels}
