from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from agents.risk_analyzer import calculate_risk_adjusted_score, calculate_risk_metrics, risk_label
from agents.technical_analyzer import (
    _compute_adx,
    _compute_atr,
    _compute_bb,
    _compute_ema,
    _compute_macd,
    _compute_rsi,
    _compute_sma,
    calculate_technical_score,
)
from utils.cache import cache
from backtesting.statistics import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_BOOTSTRAP_SEED,
    STATISTICS_VERSION,
    cost_sensitivity,
    effective_sample_size,
    historical_evidence_grade,
    validation_confidence_intervals,
)


SCHEMA_VERSION = 3


def run_our_picks_validation(
    ticker: str,
    history: Optional[pd.DataFrame] = None,
    benchmark: Optional[pd.DataFrame] = None,
    holding_days: int = 20,
    transaction_cost_bps: float = 15.0,
    slippage_bps: float = 5.0,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    try:
        from agents.deep_research import _build_trade_plan, _short_term_score

        cache_key = f"our_picks_validation_v3_{ticker}_{holding_days}_{transaction_cost_bps}_{slippage_bps}"
        if history is None and benchmark is None and not force_refresh:
            cached = cache.get(cache_key, "info", ttl=21600)
            if cached:
                return cached
        prices = _clean_history(history if history is not None else _download_history(ticker))
        spy = _clean_benchmark(benchmark if benchmark is not None else _download_history("SPY"))
        if len(prices) < 300:
            return {
                "schema_version": SCHEMA_VERSION,
                "available": False,
                "reason": "insufficient_history",
                "observations": len(prices),
            }
        signal_positions = _monthly_signal_positions(prices.index, warmup=252, holding_days=holding_days)
        samples: List[Dict[str, Any]] = []
        for position in signal_positions:
            signal_history = prices.iloc[: position + 1]
            technical = _technical_snapshot(signal_history)
            risk_metrics = calculate_risk_metrics(signal_history["Close"])
            risk_metrics["risk_level"] = risk_label(risk_metrics)
            stock = {
                "risk_penalty": calculate_risk_adjusted_score(technical["technical_score"], risk_metrics)["risk_penalty"],
                "risk_penalty_level": calculate_risk_adjusted_score(technical["technical_score"], risk_metrics)["risk_penalty_level"],
            }
            short_score = _short_term_score(stock, technical)
            avoid = {"active": stock["risk_penalty_level"] == "high"}
            trade_plan = _build_trade_plan(stock, technical, short_score, 50.0, avoid)
            stance = trade_plan.get("stance", "neutral")
            future = prices.iloc[position + 1: position + 1 + holding_days]
            if len(future) < holding_days:
                continue
            sample = simulate_trade_path(
                future,
                trade_plan,
                stance,
                transaction_cost_bps=transaction_cost_bps,
                slippage_bps=slippage_bps,
            )
            benchmark_return = _benchmark_return(spy, sample.get("entry_date"), sample.get("exit_date")) if sample.get("entered") else None
            directional_benchmark = (
                (-benchmark_return if stance == "bearish" else benchmark_return)
                if benchmark_return is not None else None
            )
            signal_date = prices.index[position].date().isoformat()
            directional_alpha = (
                sample["net_return_pct"] - directional_benchmark * 100
                if sample.get("entered") and directional_benchmark is not None else None
            )
            sample.update({
                "sample_id": f"{ticker.upper()}:{signal_date}:{stance}",
                "signal_date": signal_date,
                "short_score": short_score,
                "stance": stance,
                "benchmark_return_pct": round(benchmark_return * 100, 2) if benchmark_return is not None else None,
                "raw_benchmark_return_pct": round(benchmark_return * 100, 2) if benchmark_return is not None else None,
                "directional_benchmark_return_pct": round(directional_benchmark * 100, 2) if directional_benchmark is not None else None,
                "side_benchmark_return_pct": round(directional_benchmark * 100, 2) if directional_benchmark is not None else None,
                "directional_alpha_pct": round(directional_alpha, 2) if directional_alpha is not None else None,
                "excess_return_pct": round(directional_alpha, 2) if directional_alpha is not None else None,
                "benchmark_alignment": "exact_entry_exit_close" if benchmark_return is not None else "unavailable_or_misaligned",
            })
            samples.append(sample)
        result = summarize_validation(ticker, samples, holding_days)
        if history is None and benchmark is None:
            cache.set(cache_key, "info", result, ttl=21600)
        return result
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def simulate_trade_path(
    future: pd.DataFrame,
    trade_plan: Dict[str, Any],
    stance: str,
    transaction_cost_bps: float = 15.0,
    slippage_bps: float = 5.0,
) -> Dict[str, Any]:
    if stance not in {"bullish", "bearish"}:
        start, end = float(future["Open"].iloc[0]), float(future["Close"].iloc[-1])
        return {
            "entered": False,
            "exit_reason": "watch_only",
            "raw_return_pct": round((end / start - 1) * 100, 2),
            "absolute_move_pct": round(abs(end / start - 1) * 100, 2),
        }
    entry_zone = trade_plan["entry_zone"]
    entry = None
    entry_index = None
    entry_execution_type = None
    for index, row in future.iterrows():
        if float(row["Low"]) <= entry_zone["high"] and float(row["High"]) >= entry_zone["low"]:
            reference = entry_zone["high"] if stance == "bullish" else entry_zone["low"]
            open_in_zone = entry_zone["low"] <= float(row["Open"]) <= entry_zone["high"]
            entry = float(row["Open"]) if open_in_zone else float(reference)
            entry_execution_type = "open_in_entry_zone" if open_in_zone else "entry_zone_limit"
            entry_index = index
            break
    if entry is None:
        return {"entered": False, "exit_reason": "unfilled"}

    stop = float(trade_plan["stop_loss"])
    target1, target2 = [float(value) for value in trade_plan["targets"]]
    path = future.loc[entry_index:]
    direction = 1 if stance == "bullish" else -1
    exit_price = float(path["Close"].iloc[-1])
    exit_reason = "time"
    exit_execution_type = "holding_period_close"
    exit_index = path.index[-1]
    target1_hit = False
    ambiguous = False
    adverse_moves = []
    favorable_moves = []
    for offset, (index, row) in enumerate(path.iterrows()):
        low, high, open_price = float(row["Low"]), float(row["High"]), float(row["Open"])
        stop_hit = low <= stop if stance == "bullish" else high >= stop
        target1_today = high >= target1 if stance == "bullish" else low <= target1
        target2_today = high >= target2 if stance == "bullish" else low <= target2
        ambiguous = ambiguous or (stop_hit and (target1_today or target2_today))
        adverse_moves.append(direction * ((low if stance == "bullish" else high) / entry - 1))
        favorable_moves.append(direction * ((high if stance == "bullish" else low) / entry - 1))
        if stop_hit:
            gap_through = open_price < stop if stance == "bullish" else open_price > stop
            exit_price = open_price if offset > 0 and gap_through else stop
            exit_reason = "stop"
            exit_execution_type = "gap_open" if offset > 0 and gap_through else "stop_price"
            exit_index = index
            break
        target1_hit = target1_hit or target1_today
        if target2_today:
            exit_price = target2
            exit_reason = "target2"
            exit_execution_type = "target_limit"
            exit_index = index
            break
    gross_return = direction * (exit_price / entry - 1)
    round_trip_cost = 2 * (transaction_cost_bps + slippage_bps) / 10000
    net_return = gross_return - round_trip_cost
    return {
        "entered": True,
        "entry_date": entry_index.date().isoformat(),
        "exit_date": exit_index.date().isoformat(),
        "holding_bars": int(path.index.get_loc(exit_index)) + 1,
        "holding_calendar_days": int((pd.Timestamp(exit_index).normalize() - pd.Timestamp(entry_index).normalize()).days),
        "entry_price": round(entry, 2),
        "entry_execution_type": entry_execution_type,
        "exit_price": round(exit_price, 2),
        "exit_reason": exit_reason,
        "exit_execution_type": exit_execution_type,
        "gross_return_pct": round(gross_return * 100, 2),
        "net_return_pct": round(net_return * 100, 2),
        "transaction_cost_bps_per_side": float(transaction_cost_bps),
        "slippage_bps_per_side": float(slippage_bps),
        "transaction_cost_pct": round(2 * transaction_cost_bps / 100, 4),
        "slippage_cost_pct": round(2 * slippage_bps / 100, 4),
        "round_trip_cost_bps": round(2 * (transaction_cost_bps + slippage_bps), 4),
        "round_trip_cost_pct": round(round_trip_cost * 100, 4),
        "target1_hit": target1_hit,
        "target2_hit": exit_reason == "target2",
        "stop_hit": exit_reason == "stop",
        "ambiguous_bar": ambiguous,
        "mae_pct": round(min(adverse_moves) * 100, 2),
        "mfe_pct": round(max(favorable_moves) * 100, 2),
    }


def summarize_validation(ticker: str, samples: List[Dict[str, Any]], holding_days: int) -> Dict[str, Any]:
    entered = [sample for sample in samples if sample.get("entered")]
    returns = [sample["net_return_pct"] for sample in entered]
    equity = pd.Series([(1 + value / 100) for value in returns]).cumprod() if returns else pd.Series(dtype=float)
    max_drawdown = float((equity / equity.cummax() - 1).min() * 100) if not equity.empty else None
    cis = validation_confidence_intervals(entered)
    ess = effective_sample_size(entered, "net_return_pct")
    evidence_grade = historical_evidence_grade(entered, cis, ess)
    by_stance = {stance: _summarize_group([sample for sample in samples if sample.get("stance") == stance]) for stance in ("bullish", "bearish", "neutral")}
    return {
        "schema_version": SCHEMA_VERSION,
        "available": bool(samples),
        "ticker": ticker,
        "method": "monthly_close_signal_next_day_execution",
        "holding_days": holding_days,
        "sample_count": len(samples),
        "entered_count": len(entered),
        "benchmark_aligned_count": sum(sample.get("benchmark_alignment") == "exact_entry_exit_close" for sample in entered),
        "benchmark_misaligned_count": sum(sample.get("benchmark_alignment") == "unavailable_or_misaligned" for sample in entered),
        "unfilled_count": sum(sample.get("exit_reason") == "unfilled" for sample in samples),
        "win_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100, 1) if returns else None,
        "average_return_pct": round(float(np.mean(returns)), 2) if returns else None,
        "median_return_pct": round(float(np.median(returns)), 2) if returns else None,
        "average_excess_return_pct": _mean_present(entered, "excess_return_pct"),
        "average_directional_alpha_pct": _mean_present(entered, "directional_alpha_pct"),
        "max_drawdown_pct": round(max_drawdown, 2) if max_drawdown is not None else None,
        "target1_hit_rate_pct": _rate(entered, "target1_hit"),
        "target2_hit_rate_pct": _rate(entered, "target2_hit"),
        "stop_hit_rate_pct": _rate(entered, "stop_hit"),
        "worst_mae_pct": round(min((sample["mae_pct"] for sample in entered), default=0), 2) if entered else None,
        "ambiguous_bar_count": sum(bool(sample.get("ambiguous_bar")) for sample in entered),
        "confidence_intervals": cis,
        "effective_sample_size": ess,
        "cost_sensitivity": cost_sensitivity(entered),
        "historical_evidence_grade": evidence_grade,
        "confidence": evidence_grade,
        "by_stance": by_stance,
        "samples": samples,
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "statistics_version": STATISTICS_VERSION,
            "bootstrap_seed": DEFAULT_BOOTSTRAP_SEED,
            "bootstrap_iterations": DEFAULT_BOOTSTRAP_ITERATIONS,
            "benchmark_method": "exact_entry_exit_same_date_close_to_close_proxy",
            "evidence_scope": "ticker_specific_current_universe",
        },
        "limitations": [
            "technical_signals_only",
            "current_universe_survivorship_bias",
            "ticker_selection_bias",
            "daily_bar_stop_first",
            "benchmark_close_proxy_not_intraday_execution",
            "historical_results_not_out_of_sample_portfolio_validation",
        ],
    }


def _technical_snapshot(history: pd.DataFrame) -> Dict[str, Any]:
    close, high, low, volume = history["Close"], history["High"], history["Low"], history["Volume"]
    macd_line, macd_signal, macd_hist = _compute_macd(close)
    bb_upper, bb_lower = _compute_bb(close)
    technical = {
        "price": float(close.iloc[-1]), "rsi_14": _compute_rsi(close),
        "macd_line": macd_line, "macd_signal": macd_signal, "macd_histogram": macd_hist,
        "bb_upper": bb_upper, "bb_lower": bb_lower, "sma_20": _compute_sma(close, 20),
        "sma_50": _compute_sma(close, 50), "sma_200": _compute_sma(close, 200),
        "ema_9": _compute_ema(close, 9), "ema_21": _compute_ema(close, 21),
        "ema_50": _compute_ema(close, 50), "ema_200": _compute_ema(close, 200),
        "atr_14": _compute_atr(high, low, close), "adx_14": _compute_adx(high, low, close),
        "volume_ratio_10_50": float(volume.tail(10).mean() / volume.tail(50).mean()) if volume.tail(50).mean() > 0 else None,
    }
    technical["technical_score"] = calculate_technical_score(technical)
    return technical


def _monthly_signal_positions(index: pd.DatetimeIndex, warmup: int, holding_days: int) -> List[int]:
    positions = []
    last_position = -holding_days
    period_index = index.tz_localize(None) if index.tz is not None else index
    periods = pd.Series(range(len(index)), index=index).groupby(period_index.to_period("M")).last()
    for position in periods.tolist():
        if position >= warmup and position - last_position >= holding_days and position + holding_days < len(index):
            positions.append(int(position))
            last_position = int(position)
    return positions


def _clean_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()
    frame = history.copy()
    required = ["Open", "High", "Low", "Close", "Volume"]
    frame = frame[required].apply(pd.to_numeric, errors="coerce").dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


def _download_history(ticker: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(period="5y", auto_adjust=True)


def _clean_benchmark(benchmark: pd.DataFrame) -> pd.DataFrame:
    if benchmark is None or benchmark.empty or "Close" not in benchmark:
        return pd.DataFrame()
    frame = benchmark[["Close"]].copy()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    return frame.dropna(subset=["Close"]).sort_index()


def _benchmark_return(benchmark: pd.DataFrame, start: Any, end: Any) -> Optional[float]:
    if benchmark.empty or start is None or end is None or "Close" not in benchmark:
        return None
    normalized = benchmark.copy()
    normalized.index = pd.DatetimeIndex(normalized.index).tz_localize(None).normalize()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    start_date = pd.Timestamp(start).tz_localize(None).normalize()
    end_date = pd.Timestamp(end).tz_localize(None).normalize()
    if start_date not in normalized.index or end_date not in normalized.index:
        return None
    start_close = pd.to_numeric(normalized.at[start_date, "Close"], errors="coerce")
    end_close = pd.to_numeric(normalized.at[end_date, "Close"], errors="coerce")
    if not np.isfinite(start_close) or not np.isfinite(end_close) or start_close <= 0:
        return None
    return float(end_close / start_close - 1)


def _summarize_group(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    entered = [sample for sample in samples if sample.get("entered")]
    returns = [sample["net_return_pct"] for sample in entered]
    return {
        "sample_count": len(samples), "entered_count": len(entered),
        "win_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100, 1) if returns else None,
        "average_return_pct": round(float(np.mean(returns)), 2) if returns else None,
        "average_excess_return_pct": _mean_present(entered, "excess_return_pct"),
        "target1_hit_rate_pct": _rate(entered, "target1_hit"),
        "stop_hit_rate_pct": _rate(entered, "stop_hit"),
        "confidence": _confidence_level(entered),
    }


def _confidence_level(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(samples) < 12:
        return {"level": "insufficient", "score": 0, "reason": "fewer_than_12_trades"}
    win_rate = sum(sample["net_return_pct"] > 0 for sample in samples) / len(samples)
    average = float(np.mean([sample["net_return_pct"] for sample in samples]))
    excess = float(np.mean([sample["excess_return_pct"] for sample in samples]))
    score = (25 if len(samples) >= 24 else 15) + (30 if win_rate >= 0.55 else 15 if win_rate >= 0.5 else 0) + (25 if average > 0 else 0) + (20 if excess > 0 else 0)
    if average <= 0 or excess <= 0:
        level = "low"
    else:
        level = "high" if score >= 80 else "medium" if score >= 55 else "low"
    return {"level": level, "score": score, "reason": "sample_performance_quality"}


def _rate(samples: List[Dict[str, Any]], key: str) -> Optional[float]:
    return round(sum(bool(sample.get(key)) for sample in samples) / len(samples) * 100, 1) if samples else None


def _mean_present(samples: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [float(sample[key]) for sample in samples if sample.get(key) is not None]
    return round(float(np.mean(values)), 2) if values else None
