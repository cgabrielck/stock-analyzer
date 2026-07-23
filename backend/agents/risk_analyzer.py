"""Historical risk metrics for research use, calculated from adjusted daily prices."""

from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MIN_RETURN_OBSERVATIONS = 60
RISK_LOOKBACK_PRICES = 126


def calculate_risk_metrics(
    prices: pd.Series,
    benchmark_prices: Optional[pd.Series] = None,
    risk_free_rate: float = 0.0,
) -> Dict[str, Any]:
    """Calculate annualized risk statistics without fetching external data."""
    clean_prices = pd.to_numeric(prices, errors="coerce")
    clean_prices = clean_prices[np.isfinite(clean_prices) & (clean_prices > 0)]
    if clean_prices.index.has_duplicates:
        clean_prices = clean_prices[~clean_prices.index.duplicated(keep="last")]
    clean_prices = clean_prices.sort_index().tail(RISK_LOOKBACK_PRICES)
    returns = clean_prices.pct_change().dropna()
    if len(returns) < MIN_RETURN_OBSERVATIONS:
        return {"available": False, "observations": len(returns), "reason": "insufficient_history"}

    daily_rf = (1 + risk_free_rate) ** (1 / TRADING_DAYS) - 1
    daily_vol = float(returns.std(ddof=1))
    annual_return = float((1 + returns).prod() ** (TRADING_DAYS / len(returns)) - 1)
    annual_volatility = daily_vol * np.sqrt(TRADING_DAYS)
    excess_returns = returns - daily_rf
    sharpe = float(excess_returns.mean() / daily_vol * np.sqrt(TRADING_DAYS)) if daily_vol > 0 else None
    downside = excess_returns[excess_returns < 0]
    sortino = (
        float(excess_returns.mean() / downside.std(ddof=1) * np.sqrt(TRADING_DAYS))
        if len(downside) > 1 and downside.std(ddof=1) > 0 else None
    )
    var_95 = float(np.percentile(returns, 5))
    cumulative = (1 + returns).cumprod()
    max_drawdown = float((cumulative / cumulative.cummax() - 1).min())

    beta = None
    if benchmark_prices is not None:
        benchmark_returns = pd.to_numeric(benchmark_prices, errors="coerce").pct_change()
        aligned = pd.concat([returns, benchmark_returns], axis=1, sort=False).dropna()
        if len(aligned) >= MIN_RETURN_OBSERVATIONS and aligned.iloc[:, 1].var(ddof=1) > 0:
            beta = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / aligned.iloc[:, 1].var(ddof=1))

    return {
        "available": True,
        "observations": len(returns),
        "annual_return_pct": round(float(annual_return * 100), 2),
        "annual_volatility_pct": round(float(annual_volatility * 100), 2),
        "var_95_daily_pct": round(float(var_95 * 100), 2),
        "max_drawdown_pct": round(float(max_drawdown * 100), 2),
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 2) if sortino is not None else None,
        "beta": round(beta, 2) if beta is not None else None,
    }


def risk_label(metrics: Dict[str, Any]) -> str:
    if not metrics.get("available"):
        return "unknown"
    volatility = abs(metrics.get("annual_volatility_pct") or 0)
    drawdown = abs(metrics.get("max_drawdown_pct") or 0)
    beta = abs(metrics.get("beta") or 1)
    if volatility >= 45 or drawdown >= 50 or beta >= 1.6:
        return "high"
    if volatility >= 25 or drawdown >= 25 or beta >= 1.2:
        return "medium"
    return "low"


def calculate_risk_adjusted_score(total_score: float, metrics: Dict[str, Any]) -> Dict[str, Any]:
    score = max(0.0, min(100.0, float(total_score or 0)))
    if not metrics.get("available"):
        return {
            "risk_adjusted_score": round(score, 1),
            "risk_penalty": 0.0,
            "risk_penalty_level": "unknown",
        }

    volatility = abs(float(metrics.get("annual_volatility_pct") or 0))
    drawdown = abs(float(metrics.get("max_drawdown_pct") or 0))
    if volatility >= 45 or drawdown >= 50:
        penalty, level = 10.0, "high"
    elif volatility >= 25 or drawdown >= 25:
        penalty, level = 5.0, "medium"
    else:
        penalty, level = 0.0, "low"
    return {
        "risk_adjusted_score": round(max(0.0, score - penalty), 1),
        "risk_penalty": penalty,
        "risk_penalty_level": level,
    }


def fetch_risk_metrics(tickers: Iterable[str], period: str = "1y") -> Dict[str, Dict[str, Any]]:
    """Fetch one adjusted-price panel and calculate risk against SPY for each ticker."""
    ticker_list = list(dict.fromkeys(t for t in tickers if t))
    if not ticker_list:
        return {}
    try:
        import yfinance as yf

        data = yf.download(ticker_list + ["SPY"], period=period, auto_adjust=True, progress=False)
        close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
        if isinstance(close, pd.Series):
            close = close.to_frame(name=ticker_list[0])
        benchmark = close["SPY"] if "SPY" in close else None
        result: Dict[str, Dict[str, Any]] = {}
        for ticker in ticker_list:
            if ticker not in close:
                result[ticker] = {"available": False, "reason": "price_unavailable"}
                continue
            metrics = calculate_risk_metrics(close[ticker], benchmark)
            metrics["risk_level"] = risk_label(metrics)
            result[ticker] = metrics
        return result
    except Exception as exc:
        return {ticker: {"available": False, "reason": str(exc), "risk_level": "unknown"} for ticker in ticker_list}


def calculate_portfolio_risk(
    price_history: pd.DataFrame, market_values: Dict[str, float], cash: float = 0.0,
) -> Dict[str, Any]:
    """Calculate cash-aware covariance risk using current position market values."""
    values = {
        ticker: float(value) for ticker, value in market_values.items()
        if isinstance(value, (int, float)) and np.isfinite(value) and value > 0
    }
    if not values:
        return {"available": False, "reason": "no_positions", "stress_tests": []}
    equity_value = sum(values.values())
    portfolio_value = equity_value + max(0.0, float(cash or 0))
    actual_weights = {ticker: value / portfolio_value for ticker, value in values.items()}
    stress_tests = []
    for scenario, shock in (("market_correction_10", -0.10), ("bear_market_20", -0.20)):
        pnl = equity_value * shock
        stress_tests.append({
            "scenario": scenario, "equity_shock_pct": shock * 100, "pnl": round(pnl, 2),
            "portfolio_change_pct": round(pnl / portfolio_value * 100, 2),
            "stressed_value": round(portfolio_value + pnl, 2),
        })

    prices = price_history.copy() if isinstance(price_history, pd.DataFrame) else pd.DataFrame()
    prices = prices[~prices.index.duplicated(keep="last")].sort_index().tail(RISK_LOOKBACK_PRICES)
    excluded: Dict[str, str] = {}
    eligible = []
    returns_by_ticker = {}
    for ticker in sorted(values, key=values.get, reverse=True):
        if ticker not in prices:
            excluded[ticker] = "price_unavailable"
            continue
        series = pd.to_numeric(prices[ticker], errors="coerce")
        series = series.where(np.isfinite(series) & (series > 0))
        returns = series.pct_change(fill_method=None)
        if returns.notna().sum() < MIN_RETURN_OBSERVATIONS:
            excluded[ticker] = "insufficient_history"
            continue
        candidate = eligible + [ticker]
        candidate_frame = pd.concat([returns_by_ticker.get(t, returns if t == ticker else None) for t in candidate], axis=1)
        candidate_frame.columns = candidate
        if len(candidate_frame.dropna()) < MIN_RETURN_OBSERVATIONS:
            excluded[ticker] = "insufficient_overlap"
            continue
        eligible.append(ticker)
        returns_by_ticker[ticker] = returns

    covered_value = sum(values[ticker] for ticker in eligible)
    base = {
        "actual_weights": {ticker: round(weight, 6) for ticker, weight in actual_weights.items()},
        "cash_weight_pct": round(max(0.0, float(cash or 0)) / portfolio_value * 100, 2),
        "equity_coverage_pct": round(covered_value / equity_value * 100, 2),
        "portfolio_coverage_pct": round(covered_value / portfolio_value * 100, 2),
        "coverage_status": "full" if len(eligible) == len(values) else "partial" if eligible else "none",
        "covered_tickers": eligible, "excluded_tickers": excluded, "stress_tests": stress_tests,
    }
    if not eligible:
        return {"available": False, "reason": "insufficient_history", "observations": 0, **base}
    aligned = pd.concat([returns_by_ticker[ticker] for ticker in eligible], axis=1).dropna()
    aligned.columns = eligible
    weights = np.array([actual_weights[ticker] for ticker in eligible])
    covariance = aligned.cov().to_numpy()
    variance = float(weights @ covariance @ weights)
    portfolio_returns = aligned.to_numpy() @ weights
    cumulative = pd.Series(1 + portfolio_returns).cumprod()
    return {
        "available": True, "observations": len(aligned),
        "annual_volatility_pct": round(float(np.sqrt(max(variance, 0)) * np.sqrt(TRADING_DAYS) * 100), 2),
        "var_95_daily_pct": round(float(np.percentile(portfolio_returns, 5)) * 100, 2),
        "max_drawdown_pct": round(float((cumulative / cumulative.cummax() - 1).min()) * 100, 2),
        **base,
    }
