"""
Backtesting engine for the stock analyzer scoring system.

Validates whether the scoring system's recommendations would have
outperformed the market (SPY) historically.

Methodology:
  - Monthly rebalancing at each month-end
  - For each rebalance date:
      1. Technical indicators from price data up to that date (no look-ahead)
      2. Fundamental data from the most recent quarterly report with filing lag
      3. Combined scoring matching the main system
      4. Top 5 stocks selected with sector diversification (max 2 per sector)
  - Track forward 1-month performance vs SPY
"""

import math
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from agents.technical_analyzer import (
    _compute_rsi,
    _compute_macd,
    _compute_sma,
    _compute_bb,
    _compute_atr,
)
from utils.cache import cache
from utils.constants import STOCK_UNIVERSE, SCORING_WEIGHTS

FILING_LAG_DAYS: int = 60
MAX_WORKERS: int = 5
DEFAULT_START: str = "2020-01-01"
TECH_CANDIDATES: int = 15
ENTRY_THRESHOLD: float = 50.0
MAX_PER_SECTOR: int = 2
TOP_N: int = 5

ProgressCb = Optional[Callable[[int, int, str], None]]


# ---------------------------------------------------------------------------
# Historical data fetching
# ---------------------------------------------------------------------------

def _fetch_single_price(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start=start, end=end)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return None


def fetch_price_data(
    tickers: List[str],
    start: str = DEFAULT_START,
    end: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    end = end or datetime.now().strftime("%Y-%m-%d")
    results: Dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_single_price, t, start, end): t for t in tickers}
        for future in as_completed(futures):
            t = futures[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    results[t] = df
            except Exception:
                pass
    return results


def _fetch_single_fundamentals(ticker: str) -> Optional[pd.DataFrame]:
    cached = cache.get(f"bt_fund_{ticker}", "financials")
    if cached is not None:
        return pd.DataFrame(cached) if isinstance(cached, dict) else cached
    try:
        stock = yf.Ticker(ticker)
        qf = stock.quarterly_financials
        if qf is not None and not qf.empty:
            cache.set(f"bt_fund_{ticker}", "financials", qf.to_dict())
            return qf
    except Exception:
        pass
    return None


def _fetch_single_balance_sheet(ticker: str) -> Optional[pd.DataFrame]:
    cached = cache.get(f"bt_bs_{ticker}", "financials")
    if cached is not None:
        return pd.DataFrame(cached) if isinstance(cached, dict) else cached
    try:
        stock = yf.Ticker(ticker)
        bs = stock.quarterly_balance_sheet
        if bs is not None and not bs.empty:
            cache.set(f"bt_bs_{ticker}", "financials", bs.to_dict())
            return bs
    except Exception:
        pass
    return None


def _find_recent_quarter(qf: pd.DataFrame, as_of: pd.Timestamp) -> Tuple[int, int]:
    cutoff = as_of - timedelta(days=FILING_LAG_DAYS)
    available = [c for c in qf.columns if pd.Timestamp(c) <= cutoff]
    if not available:
        available = [qf.columns[-1]]
    col = min(available, key=lambda c: abs((pd.Timestamp(c) - cutoff).days))
    idx = list(qf.columns).index(col)
    prev = min(idx + 1, len(qf.columns) - 1)
    return idx, prev


def _extract_fundamentals_as_of(
    qf: pd.DataFrame,
    bs: Optional[pd.DataFrame],
    price_df: Optional[pd.DataFrame],
    as_of: pd.Timestamp,
) -> Dict[str, Any]:
    if qf is None or qf.empty:
        return {}

    idx, prev = _find_recent_quarter(qf, as_of)
    result: Dict[str, Any] = {}

    try:
        rev_current = None
        rev_prev = None
        if "Total Revenue" in qf.index:
            rev_current = qf.loc["Total Revenue"].iloc[idx]
            rev_prev = qf.loc["Total Revenue"].iloc[prev]
            if pd.notna(rev_current) and pd.notna(rev_prev) and rev_prev != 0:
                result["revenue_growth"] = float((rev_current / rev_prev - 1) * 100)

        ni = None
        if "Net Income" in qf.index:
            ni = qf.loc["Net Income"].iloc[idx]
            if pd.notna(ni):
                result["net_income"] = float(ni)

        if rev_current is not None and ni is not None and pd.notna(rev_current) and pd.notna(ni) and rev_current != 0:
            result["profit_margin"] = float((ni / rev_current) * 100)

        eps_current = None
        eps_prev = None
        if "Diluted EPS" in qf.index:
            eps_current = qf.loc["Diluted EPS"].iloc[idx]
            eps_prev = qf.loc["Diluted EPS"].iloc[prev]
            if pd.notna(eps_current) and pd.notna(eps_prev) and eps_prev != 0:
                result["eps_growth"] = float((eps_current / eps_prev - 1) * 100)

        if bs is not None and not bs.empty:
            bs_idx = idx if idx < len(bs.columns) else len(bs.columns) - 1
            equity = None
            if "Stockholders Equity" in bs.index:
                eq_val = bs.loc["Stockholders Equity"].iloc[bs_idx]
                if pd.notna(eq_val):
                    equity = float(eq_val)
                    if ni is not None and pd.notna(ni) and equity != 0:
                        result["roe"] = float((ni / equity) * 100)

            total_debt = None
            if "Total Debt" in bs.index:
                td_val = bs.loc["Total Debt"].iloc[bs_idx]
                if pd.notna(td_val):
                    total_debt = float(td_val)

            if "Long Term Debt" in bs.index and total_debt is None:
                ltd = bs.loc["Long Term Debt"].iloc[bs_idx]
                if pd.notna(ltd):
                    total_debt = float(ltd)

            if total_debt is not None and equity is not None and equity != 0:
                result["debt_equity"] = round(total_debt / equity, 4)

        if price_df is not None and not price_df.empty:
            current_price = float(price_df["Close"].iloc[-1])
            if current_price > 0 and eps_current is not None and pd.notna(eps_current) and eps_current != 0:
                pe = current_price / abs(float(eps_current)) if eps_current != 0 else None
                eps_g = result.get("eps_growth", 0)
                if pe is not None and eps_g and eps_g > 0:
                    result["peg"] = round(pe / (eps_g / 100.0), 2)

    except (IndexError, KeyError):
        pass

    return result


# ---------------------------------------------------------------------------
# Technical scoring on historical data
# ---------------------------------------------------------------------------

def _score_stock_technical(hist: pd.DataFrame, ticker: str) -> Dict[str, Any]:
    if len(hist) < 50:
        return {"ticker": ticker, "score": 0, "error": "insufficient_history"}

    close = hist["Close"]
    volume = hist["Volume"]
    high = hist["High"]
    low = hist["Low"]

    current_price = float(close.iloc[-1])

    rsi = _compute_rsi(close, 14)
    macd_line, macd_signal, macd_hist = _compute_macd(close)
    bb_upper, bb_lower = _compute_bb(close)
    sma20 = _compute_sma(close, 20)
    sma50 = _compute_sma(close, 50)
    atr = _compute_atr(high, low, close)

    price_vs_sma50 = ((current_price / sma50) - 1) * 100 if sma50 and sma50 > 0 else None

    vol_short = float(volume.tail(10).mean())
    vol_long = float(volume.tail(50).mean())
    volume_ratio = vol_short / vol_long if vol_long > 0 else None

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
        if macd_hist > 0:
            total += 15
        else:
            total += 5

    if volume_ratio is not None:
        if volume_ratio > 0.8:
            total += 10
        elif volume_ratio < 0.5:
            total += 5

    if price_vs_sma50 is not None:
        if -5 <= price_vs_sma50 <= 5:
            total += 10
        elif price_vs_sma50 > 5:
            total += 5
        elif price_vs_sma50 < -15:
            total -= 5

    if bb_lower and bb_upper and current_price:
        if current_price <= bb_lower:
            total += 15
        elif current_price >= bb_upper:
            total += 5

    total = max(0, min(100, total))

    return {
        "ticker": ticker,
        "total_score": round(total, 1),
        "price": current_price,
        "rsi_14": rsi,
        "macd_histogram": macd_hist,
        "sma_20": sma20,
        "sma_50": sma50,
        "atr_14": atr,
        "volume_ratio_10_50": volume_ratio,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "trend_signal": "uptrend" if sma50 and current_price > sma50 else "downtrend",
    }


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

class BacktestResult:
    def __init__(self) -> None:
        self.periods: List[Dict[str, Any]] = []
        self.tickers_picked: Dict[str, int] = {}
        self.sector_counts: Dict[str, int] = {}
        self.total_periods: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.total_return_pct: float = 0.0
        self.spy_return_pct: float = 0.0
        self.avg_alpha_pct: float = 0.0
        self.max_drawdown_pct: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.win_rate_pct: float = 0.0
        self.best_month_pct: float = 0.0
        self.worst_month_pct: float = 0.0
        self.volatility_pct: float = 0.0

    @property
    def num_periods(self) -> int:
        return len(self.periods)


def run_backtest(
    start: str = DEFAULT_START,
    end: Optional[str] = None,
    use_fundamentals: bool = True,
    progress_callback=None,
) -> BacktestResult:
    end_date = end or datetime.now().strftime("%Y-%m-%d")
    result = BacktestResult()

    tickers = [s["ticker"] for s in STOCK_UNIVERSE]
    all_tickers = tickers + ["SPY"]

    if progress_callback:
        progress_callback(1, 0, "Fetching historical prices...")

    price_data = fetch_price_data(all_tickers, start, end_date)

    if "SPY" not in price_data:
        result.periods = []
        return result

    if progress_callback:
        progress_callback(1, 0, "Computing rebalance dates...")

    rebalance_dates = list(pd.date_range(
        start=pd.Timestamp(start) + pd.DateOffset(months=1),
        end=pd.Timestamp(end_date),
        freq="ME",
    ))

    sample_tz = next((df.index.tz for df in price_data.values() if df is not None and not df.empty), None)
    reb_dates_tz = [d.tz_localize(sample_tz) if sample_tz else d for d in rebalance_dates]

    sector_map = {s["ticker"]: s["sector"] for s in STOCK_UNIVERSE}

    fund_data: Dict[str, Optional[pd.DataFrame]] = {}
    bs_data: Dict[str, Optional[pd.DataFrame]] = {}
    if use_fundamentals:
        if progress_callback:
            progress_callback(1, 0, "Fetching quarterly fundamentals & balance sheets...")
        for t in tickers:
            fund_data[t] = _fetch_single_fundamentals(t)
            bs_data[t] = _fetch_single_balance_sheet(t)

    portfolio_values: List[float] = []
    spy_values: List[float] = []

    for i, (reb_date, reb_date_tz) in enumerate(zip(rebalance_dates, reb_dates_tz)):
        if progress_callback:
            progress_callback(i + 1, len(rebalance_dates),
                              f"Rebalancing {reb_date.date()}...")

        scored: List[Dict[str, Any]] = []

        for ticker in tickers:
            df = price_data.get(ticker)
            if df is None or df.empty:
                continue
            hist = df[df.index <= reb_date_tz]
            if len(hist) < 50:
                continue

            tech = _score_stock_technical(hist, ticker)
            if tech.get("error"):
                continue

            tech_score = tech.get("total_score", 0)
            score = tech_score
            fund_score: Optional[float] = None

            if use_fundamentals and ticker in fund_data:
                qf = fund_data[ticker]
                if qf is not None:
                    fund = _extract_fundamentals_as_of(qf, bs_data.get(ticker), df, reb_date)
                    fund["ticker"] = ticker
                    fund["sector"] = sector_map.get(ticker, "Unknown")

                    from agents.fundamental_analyzer import calculate_growth_score
                    gscore_val, details, metrics_used = calculate_growth_score(fund)
                    if metrics_used > 0:
                        fund_score = gscore_val
                        score = round(gscore_val * 0.7 + tech_score * 0.3, 1)

            entry = {
                "ticker": ticker,
                "sector": sector_map.get(ticker, "Unknown"),
                "total_score": score,
                "tech_score": tech_score,
                "fund_score": fund_score,
                "price": tech.get("price"),
                "rsi_14": tech.get("rsi_14"),
                "macd_histogram": tech.get("macd_histogram"),
                "sma_20": tech.get("sma_20"),
                "sma_50": tech.get("sma_50"),
                "trend_signal": tech.get("trend_signal"),
            }
            scored.append(entry)

        scored.sort(key=lambda x: x.get("total_score", 0) or 0, reverse=True)

        sector_count: Dict[str, int] = {}
        picks: List[Dict[str, Any]] = []
        for s in scored:
            sec = s.get("sector", "Unknown")
            if sector_count.get(sec, 0) < MAX_PER_SECTOR:
                picks.append(s)
                sector_count[sec] = sector_count.get(sec, 0) + 1
            if len(picks) >= TOP_N:
                break

        next_date_tz = reb_date_tz + pd.DateOffset(months=1)
        pick_returns: List[float] = []
        for pick in picks:
            ticker = pick["ticker"]
            entry_price = pick.get("price")
            if entry_price is None:
                continue

            df = price_data.get(ticker)
            if df is None:
                continue

            exit_slice = df[(df.index > reb_date_tz) & (df.index <= next_date_tz)]
            if not exit_slice.empty:
                exit_price = float(exit_slice["Close"].iloc[-1])
                ret = (exit_price / entry_price - 1) * 100
                pick_returns.append(ret)

            result.tickers_picked[ticker] = result.tickers_picked.get(ticker, 0) + 1

        for pick in picks:
            sec = pick.get("sector", "Unknown")
            result.sector_counts[sec] = result.sector_counts.get(sec, 0) + 1

        spy_df = price_data.get("SPY")
        spy_ret = None
        if spy_df is not None:
            spy_entry_slice = spy_df[spy_df.index <= reb_date_tz]
            spy_exit_slice = spy_df[(spy_df.index > reb_date_tz) & (spy_df.index <= next_date_tz)]
            if not spy_entry_slice.empty and not spy_exit_slice.empty:
                spy_entry = float(spy_entry_slice["Close"].iloc[-1])
                spy_exit = float(spy_exit_slice["Close"].iloc[-1])
                spy_ret = (spy_exit / spy_entry - 1) * 100

        fund_scores = [p.get("fund_score") for p in picks if p.get("fund_score") is not None]
        period = {
            "date": reb_date,
            "picks": [p["ticker"] for p in picks],
            "avg_score": round(sum(p.get("total_score", 0) for p in picks) / len(picks), 1) if picks else 0,
            "avg_tech_score": round(sum(p.get("tech_score", 0) for p in picks) / len(picks), 1) if picks else 0,
            "avg_fund_score": round(sum(fund_scores) / len(fund_scores), 1) if fund_scores else None,
            "num_picks": len(picks),
            "avg_return": round(sum(pick_returns) / len(pick_returns), 2) if pick_returns else None,
            "spy_return": round(spy_ret, 2) if spy_ret is not None else None,
        }

        if period["avg_return"] is not None and period["spy_return"] is not None:
            period["alpha"] = round(period["avg_return"] - period["spy_return"], 2)
            period["beat_spy"] = period["avg_return"] > period["spy_return"]
            result.total_periods += 1
            if period["beat_spy"]:
                result.wins += 1
            else:
                result.losses += 1

        result.periods.append(period)

        if pick_returns:
            avg_ret = sum(pick_returns) / len(pick_returns)
            if portfolio_values:
                portfolio_values.append(portfolio_values[-1] * (1 + avg_ret / 100))
            else:
                portfolio_values.append(10000 * (1 + avg_ret / 100))

        if spy_ret is not None:
            if spy_values:
                spy_values.append(spy_values[-1] * (1 + spy_ret / 100))
            else:
                spy_values.append(10000 * (1 + spy_ret / 100))

    _compute_aggregate_metrics(result, portfolio_values, spy_values)
    return result


def _compute_aggregate_metrics(
    result: BacktestResult,
    portfolio_values: List[float],
    spy_values: List[float],
) -> None:
    valid = [p for p in result.periods if p.get("avg_return") is not None]
    if not valid:
        return

    spy_valid = [p for p in valid if p.get("spy_return") is not None]

    result.win_rate_pct = round(result.wins / result.total_periods * 100, 1) if result.total_periods > 0 else 0.0

    returns = [p["avg_return"] for p in valid if p["avg_return"] is not None]
    spy_returns = [p["spy_return"] for p in spy_valid if p["spy_return"] is not None]

    result.avg_alpha_pct = round(
        sum(p.get("alpha", 0) for p in valid if p.get("alpha") is not None) / len(valid), 2
    )

    if portfolio_values:
        result.total_return_pct = round((portfolio_values[-1] / 10000 - 1) * 100, 2)

    if spy_values:
        result.spy_return_pct = round((spy_values[-1] / 10000 - 1) * 100, 2)

    if returns:
        result.best_month_pct = round(max(returns), 2)
        result.worst_month_pct = round(min(returns), 2)

        returns_arr = np.array(returns)
        result.volatility_pct = round(float(np.std(returns_arr)), 2)

        if result.volatility_pct > 0:
            risk_free = 0.0
            excess = np.mean(returns_arr) - risk_free
            result.sharpe_ratio = round(float(excess / np.std(returns_arr)), 2)

        if portfolio_values:
            peak = portfolio_values[0]
            max_dd = 0.0
            for v in portfolio_values:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            result.max_drawdown_pct = round(max_dd, 2)

    result.total_periods = len(valid)


def format_backtest_summary(result: BacktestResult) -> Dict[str, Any]:
    return {
        "total_periods": result.total_periods,
        "win_rate": result.win_rate_pct,
        "wins": result.wins,
        "losses": result.losses,
        "total_return": result.total_return_pct,
        "spy_return": result.spy_return_pct,
        "avg_alpha": result.avg_alpha_pct,
        "max_drawdown": result.max_drawdown_pct,
        "sharpe": result.sharpe_ratio,
        "best_month": result.best_month_pct,
        "worst_month": result.worst_month_pct,
        "volatility": result.volatility_pct,
        "periods": result.periods,
        "tickers_picked": dict(sorted(result.tickers_picked.items(), key=lambda x: x[1], reverse=True)[:20]),
        "sector_counts": result.sector_counts,
    }
