from typing import Any, Dict, List, Optional, Tuple
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
JOURNAL_PATH = os.path.join(DATA_DIR, "trade_journal.json")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio_state.json")

DEFAULT_STOP_LOSS_PCT = 0.10
DEFAULT_UPISDE_PCT = 0.15
MAX_KELLY_FRACTION = 0.25
TOTAL_ALLOCATION = 0.90
CORR_THRESHOLD = 0.80


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def kelly_fraction(win_prob: float, upside_pct: float, downside_pct: float = DEFAULT_STOP_LOSS_PCT) -> float:
    if downside_pct <= 0 or upside_pct <= 0:
        return 0
    b = upside_pct / downside_pct
    q = 1 - win_prob
    if b <= 0:
        return 0
    f = (win_prob * b - q) / b
    return max(0.0, min(f, MAX_KELLY_FRACTION))


def compute_correlations(tickers: List[str], period: str = "1y") -> Tuple[Optional[pd.DataFrame], List[Tuple[str, str, float]]]:
    valid = [t for t in tickers if t]
    if len(valid) < 2:
        return None, []

    try:
        data = yf.download(valid, period=period, progress=False, auto_adjust=True)
        if data.empty:
            return None, []
        close = data["Close"] if "Close" in data.columns else data
        returns = close.pct_change().dropna()
        if returns.empty or returns.shape[1] < 2:
            return None, []
        corr = returns.corr()
        high_pairs: List[Tuple[str, str, float]] = []
        for i in range(len(corr.columns)):
            for j in range(i + 1, len(corr.columns)):
                val = corr.iloc[i, j]
                if abs(val) >= CORR_THRESHOLD:
                    high_pairs.append((corr.columns[i], corr.columns[j], round(val, 3)))
        return corr, high_pairs
    except Exception:
        return None, []


def _load_journal() -> List[Dict[str, Any]]:
    _ensure_data_dir()
    if os.path.exists(JOURNAL_PATH):
        try:
            with open(JOURNAL_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_journal(entries: List[Dict[str, Any]]) -> None:
    _ensure_data_dir()
    with open(JOURNAL_PATH, "w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _load_portfolio_state() -> Dict[str, Any]:
    _ensure_data_dir()
    if os.path.exists(PORTFOLIO_PATH):
        try:
            with open(PORTFOLIO_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_portfolio_state(state: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def log_trade(ticker: str, action: str, price: float, shares: int, reason: str = "") -> None:
    entries = _load_journal()
    entries.append({
        "date": datetime.now().isoformat(),
        "ticker": ticker,
        "action": action,
        "price": round(price, 2),
        "shares": shares,
        "reason": reason,
    })
    _save_journal(entries)


def build_portfolio(
    recommendations: List[Dict[str, Any]],
    total_capital: float = 100000.0,
) -> Dict[str, Any]:
    saved = _load_portfolio_state()
    old_positions = saved.get("positions", {})
    all_tickers = [r["ticker"] for r in recommendations]
    corr, high_pairs = compute_correlations(all_tickers)

    total_score = sum(r.get("total_score", 0) for r in recommendations)
    weights: Dict[str, float] = {}
    for r in recommendations:
        score = r.get("total_score", 0)
        if total_score <= 0:
            weights[r["ticker"]] = TOTAL_ALLOCATION / max(len(recommendations), 1)
            continue

        win_prob = score / 100.0
        price = r.get("price")
        target = r.get("target_mean_price")
        if price and target and target > price:
            upside = (target / price) - 1
        else:
            upside = DEFAULT_UPISDE_PCT

        beta = r.get("beta")
        if beta and beta > 0:
            downside = min(DEFAULT_STOP_LOSS_PCT * beta, 0.25)
        else:
            downside = DEFAULT_STOP_LOSS_PCT

        f = kelly_fraction(win_prob, upside, downside)
        weights[r["ticker"]] = f

    total_weight = sum(weights.values())
    if total_weight > 0:
        scale = TOTAL_ALLOCATION / total_weight
        for t in weights:
            weights[t] = round(weights[t] * scale, 4)

    positions: List[Dict[str, Any]] = []
    for r in recommendations:
        ticker = r["ticker"]
        price = r.get("price")
        if not price or price <= 0:
            continue

        weight = weights.get(ticker, 0)
        alloc = total_capital * weight
        shares = int(alloc / price)

        old = old_positions.get(ticker, {})
        entry_price = old.get("entry_price", price)
        entry_date = old.get("entry_date", datetime.now().isoformat())

        if not old:
            log_trade(ticker, "buy", price, shares, f"Portfolio allocation {weight*100:.1f}%")

        target = r.get("target_mean_price")
        beta = r.get("beta")
        if beta and beta > 0:
            stop_loss_pct = min(DEFAULT_STOP_LOSS_PCT * beta, 0.25)
        else:
            stop_loss_pct = DEFAULT_STOP_LOSS_PCT
        stop_loss = round(entry_price * (1 - stop_loss_pct), 2)

        pnl = (price - entry_price) * shares
        pnl_pct = ((price / entry_price) - 1) * 100 if entry_price > 0 else 0

        positions.append({
            "ticker": ticker,
            "name": r.get("longName") or r.get("name_cn", ticker),
            "sector": r.get("sector", ""),
            "entry_price": entry_price,
            "entry_date": entry_date,
            "current_price": price,
            "shares": shares,
            "weight": weight,
            "kelly_pct": round(weight * 100, 1),
            "stop_loss": stop_loss,
            "target_price": target,
            "total_score": r.get("total_score", 0),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_hit": price <= stop_loss,
        })

    positions.sort(key=lambda p: p["weight"], reverse=True)
    total_invested = sum(p["entry_price"] * p["shares"] for p in positions)
    total_pnl = sum(p["pnl"] for p in positions)
    portfolio_value = total_invested + total_pnl
    cash = total_capital - total_invested

    new_state = {
        "positions": {p["ticker"]: {"entry_price": p["entry_price"], "entry_date": p["entry_date"]} for p in positions},
        "capital": total_capital,
        "updated_at": datetime.now().isoformat(),
    }
    _save_portfolio_state(new_state)

    return {
        "positions": positions,
        "total_capital": total_capital,
        "total_invested": round(total_invested, 2),
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_invested * 100) if total_invested > 0 else 0, 2),
        "high_corr_pairs": high_pairs,
        "correlation_df": corr,
        "num_positions": len(positions),
    }


def get_journal() -> List[Dict[str, Any]]:
    return _load_journal()


def reset_portfolio(capital: float = 100000.0) -> Dict[str, Any]:
    _ensure_data_dir()
    state = {
        "positions": {},
        "capital": capital,
        "updated_at": datetime.now().isoformat(),
    }
    _save_portfolio_state(state)
    entries = _load_journal()
    if entries:
        entries.append({
            "date": datetime.now().isoformat(),
            "ticker": "PORTFOLIO",
            "action": "reset",
            "price": 0,
            "shares": 0,
            "reason": "Portfolio reset",
        })
        _save_journal(entries)
    return state
