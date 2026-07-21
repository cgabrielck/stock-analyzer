"""Historical risk metrics for research use, calculated from adjusted daily prices."""

from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MIN_RETURN_OBSERVATIONS = 60


def calculate_risk_metrics(
    prices: pd.Series,
    benchmark_prices: Optional[pd.Series] = None,
    risk_free_rate: float = 0.0,
) -> Dict[str, Any]:
    """Calculate annualized risk statistics without fetching external data."""
    clean_prices = pd.to_numeric(prices, errors="coerce").dropna()
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
        "annual_return_pct": round(annual_return * 100, 2),
        "annual_volatility_pct": round(annual_volatility * 100, 2),
        "var_95_daily_pct": round(var_95 * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
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
    price_history: pd.DataFrame, weights: Dict[str, float], benchmark_prices: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    """Calculate a weighted portfolio risk profile from a supplied price panel."""
    valid_weights = {ticker: weight for ticker, weight in weights.items() if ticker in price_history and weight > 0}
    if not valid_weights:
        return {"available": False, "reason": "no_positions"}
    returns = price_history[list(valid_weights)].pct_change().dropna(how="all").fillna(0)
    total_weight = sum(valid_weights.values())
    portfolio_returns = sum(returns[ticker] * weight / total_weight for ticker, weight in valid_weights.items())
    synthetic_prices = (1 + portfolio_returns).cumprod() * 100
    return calculate_risk_metrics(synthetic_prices, benchmark_prices)
