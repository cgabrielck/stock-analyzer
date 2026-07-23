from datetime import datetime
from typing import Any, Dict

import numpy as np
import pandas as pd

from accounts.models import SavedPlanVersion


OUTCOME_HORIZONS = (5, 20, 60)
OUTCOME_CALCULATION_VERSION = 1


def evaluate_saved_plan_outcome(
    plan: SavedPlanVersion,
    stock_history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    horizon_days: int,
    *,
    stock_source: str = "yfinance_daily_raw",
    benchmark_source: str = "yfinance_daily_raw",
    evaluated_at: datetime,
) -> Dict[str, Any]:
    if horizon_days not in OUTCOME_HORIZONS:
        raise ValueError("invalid_outcome_horizon")
    analysis_date = pd.Timestamp(plan.analysis_timestamp)
    if analysis_date.tzinfo is None:
        analysis_date = analysis_date.tz_localize("UTC")
    analysis_date = analysis_date.tz_convert("America/New_York").date()
    stock = _clean_history(stock_history)
    benchmark = _clean_history(benchmark_history)
    if stock.empty:
        return {"status": "unavailable", "reason": "stock_history_unavailable", "horizon_days": horizon_days}
    if benchmark.empty:
        return {"status": "unavailable", "reason": "benchmark_history_unavailable", "horizon_days": horizon_days}
    evaluation_time = pd.Timestamp(evaluated_at)
    if evaluation_time.tzinfo is None:
        evaluation_time = evaluation_time.tz_localize("UTC")
    today_et = evaluation_time.tz_convert("America/New_York").date()
    stock = stock[(stock.index.date > analysis_date) & (stock.index.date < today_et)]
    if len(stock) < horizon_days:
        return {
            "status": "pending", "horizon_days": horizon_days, "bars_available": len(stock),
            "bars_required": horizon_days, "remaining_bars": horizon_days - len(stock),
        }
    window = stock.iloc[:horizon_days]
    if "Stock Splits" in window and (pd.to_numeric(window["Stock Splits"], errors="coerce").fillna(0) != 0).any():
        return {"status": "blocked", "reason": "corporate_action_split_in_window", "horizon_days": horizon_days}
    previous = _clean_history(stock_history)
    previous = previous[previous.index.date <= analysis_date]
    if previous.empty:
        return {"status": "unavailable", "reason": "previous_close_unavailable", "horizon_days": horizon_days}

    anchor_date, endpoint_date = window.index[0].date(), window.index[-1].date()
    benchmark_by_date = {index.date(): row for index, row in benchmark.iterrows()}
    if anchor_date not in benchmark_by_date or endpoint_date not in benchmark_by_date:
        return {"status": "unavailable", "reason": "benchmark_alignment_unavailable", "horizon_days": horizon_days}
    benchmark_start = benchmark_by_date[anchor_date]
    benchmark_end = benchmark_by_date[endpoint_date]
    reference_price = float(window.iloc[0]["Open"])
    endpoint_price = float(window.iloc[-1]["Close"])
    benchmark_reference = float(benchmark_start["Open"])
    benchmark_endpoint = float(benchmark_end["Close"])
    raw_return = (endpoint_price / reference_price - 1) * 100
    benchmark_return = (benchmark_endpoint / benchmark_reference - 1) * 100
    stance = plan.plan_data.get("decision", {}).get("stance")
    direction = 1 if stance == "bullish" else -1 if stance == "bearish" else None
    upside = (float(window["High"].max()) / reference_price - 1) * 100
    downside = (float(window["Low"].min()) / reference_price - 1) * 100
    events = _level_events(plan.plan_data, window, float(previous.iloc[-1]["Close"]))
    return {
        "status": "complete", "horizon_days": horizon_days,
        "calculation_version": OUTCOME_CALCULATION_VERSION, "stance": stance,
        "anchor_date": str(anchor_date), "endpoint_date": str(endpoint_date), "bars_observed": horizon_days,
        "reference_price": round(reference_price, 6), "endpoint_price": round(endpoint_price, 6),
        "raw_return_pct": round(raw_return, 4), "benchmark_ticker": "SPY",
        "benchmark_reference_price": round(benchmark_reference, 6),
        "benchmark_endpoint_price": round(benchmark_endpoint, 6),
        "benchmark_return_pct": round(benchmark_return, 4), "raw_alpha_pct": round(raw_return - benchmark_return, 4),
        "directional_return_pct": round(direction * raw_return, 4) if direction else None,
        "directional_benchmark_return_pct": round(direction * benchmark_return, 4) if direction else None,
        "directional_alpha_pct": round(direction * (raw_return - benchmark_return), 4) if direction else None,
        "raw_upside_excursion_pct": round(upside, 4), "raw_downside_excursion_pct": round(downside, 4),
        "mfe_pct": round(upside if direction == 1 else -downside, 4) if direction else None,
        "mae_pct": round(downside if direction == 1 else -upside, 4) if direction else None,
        "level_events": events, "has_same_bar_conflict": bool(events["same_bar_conflicts"]),
        "stock_price_source": stock_source, "benchmark_price_source": benchmark_source,
        "source_as_of": str(window.index[-1]), "evaluated_at": evaluated_at.isoformat(),
    }


def _clean_history(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    index = pd.to_datetime(result.index, errors="coerce")
    if getattr(index, "tz", None) is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    result.index = index
    result = result[~result.index.isna()]
    result = result[~result.index.duplicated(keep="last")].sort_index()
    for column in ("Open", "High", "Low", "Close"):
        if column not in result:
            return pd.DataFrame()
        result[column] = pd.to_numeric(result[column], errors="coerce")
        result = result[np.isfinite(result[column]) & (result[column] > 0)]
    return result


def _level_events(plan_data: Dict[str, Any], window: pd.DataFrame, previous_close: float) -> Dict[str, Any]:
    levels = plan_data["alert_levels"]
    definitions = {
        "entry_zone": levels["entry_zone"], "confirmation": levels["confirmation"],
        "stop": levels["stop"], "target_1": levels["targets"][0], "target_2": levels["targets"][1],
    }
    result: Dict[str, Any] = {"same_bar_conflicts": []}
    prior_close = previous_close
    for name, definition in definitions.items():
        result[name] = {
            "hit": False, "first_date": None, "first_bar": None,
            "comparison": definition.get("comparison"), "watch_only": bool(definition.get("watch_only", False)),
        }
    for bar_number, (index, bar) in enumerate(window.iterrows(), start=1):
        hits = []
        for name, definition in definitions.items():
            if result[name]["hit"]:
                continue
            comparison = definition.get("comparison")
            if comparison == "enters_range":
                hit = float(bar["Low"]) <= float(definition["high"]) and float(bar["High"]) >= float(definition["low"])
            elif comparison == "crosses_up":
                hit = prior_close < float(definition["price"]) and float(bar["High"]) >= float(definition["price"])
            elif comparison == "crosses_down":
                hit = prior_close > float(definition["price"]) and float(bar["Low"]) <= float(definition["price"])
            elif comparison == "at_or_above":
                hit = float(bar["High"]) >= float(definition["price"])
            else:
                hit = float(bar["Low"]) <= float(definition["price"])
            if hit:
                result[name].update({"hit": True, "first_date": str(index.date()), "first_bar": bar_number})
                hits.append(name)
        if "stop" in hits and any(target in hits for target in ("target_1", "target_2")):
            result["same_bar_conflicts"].append({"date": str(index.date()), "events": hits})
        prior_close = float(bar["Close"])
    return result
