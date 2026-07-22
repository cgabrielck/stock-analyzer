from typing import Any, Callable, Dict, List, Optional

from agents.data_fetcher import fetch_news, fetch_stock_data
from agents.fundamental_analyzer import calculate_growth_score
from agents.llm_agent import suggest_trading_strategy
from agents.risk_analyzer import calculate_risk_adjusted_score
from agents.technical_analyzer import compute_technical_indicators
from utils.constants import STOCK_UNIVERSE


def analyze_ticker(ticker: str, lang: str = "zh_tw", force_refresh: bool = False) -> Dict[str, Any]:
    stock = fetch_stock_data(ticker, force_refresh=force_refresh)
    if stock.get("error"):
        return {"ticker": ticker, "error": stock["error"], "stage": "fundamental"}

    metadata = next((item for item in STOCK_UNIVERSE if item["ticker"] == ticker), {})
    for key in ("name_cn", "name_tw", "name_en", "sector", "universe_tier"):
        if metadata.get(key) is not None:
            stock[key] = metadata[key]

    growth_score, details, metrics_used = calculate_growth_score(stock)
    stock.update({
        "growth_score": growth_score,
        "total_score": growth_score,
        "score_details": details,
        "metrics_used": metrics_used,
    })
    technical = compute_technical_indicators(ticker, period="1y", force_refresh=force_refresh)
    if technical.get("error"):
        return {"ticker": ticker, "error": technical["error"], "stage": "technical"}

    technical_score = technical.get("technical_score")
    if technical_score is not None:
        stock["technical_score"] = technical_score
        stock["total_score"] = round(growth_score * 0.7 + technical_score * 0.3, 1)
    stock["risk_metrics"] = technical.get("risk_metrics", {"available": False})
    stock.update(calculate_risk_adjusted_score(stock["total_score"], stock["risk_metrics"]))
    return analyze_selected_stock(stock, lang=lang, technical=technical)


def analyze_tickers(
    tickers: List[str],
    lang: str = "zh_tw",
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for index, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(ticker, index, len(tickers))
        try:
            results[ticker] = analyze_ticker(ticker, lang=lang, force_refresh=force_refresh)
        except Exception as exc:
            results[ticker] = {"ticker": ticker, "error": str(exc), "stage": "unexpected"}
    return results


def analyze_selected_stock(
    stock: Dict[str, Any], lang: str = "zh_tw", technical: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ticker = stock["ticker"]
    technical = technical or compute_technical_indicators(ticker, period="1y", force_refresh=False)
    if technical.get("error"):
        return {"ticker": ticker, "error": technical["error"]}

    short_score = _short_term_score(stock, technical)
    long_score = _long_term_score(stock, technical)
    avoid = _avoid_assessment(stock, technical, short_score, long_score)
    news = fetch_news(ticker, max_items=5)
    strategy = suggest_trading_strategy(
        ticker,
        stock,
        technical,
        technical.get("price") or stock.get("price") or 0,
        news_data=news,
        lang=lang,
    )
    return {
        "ticker": ticker,
        "short_term": {
            "score": short_score,
            "view": _view(short_score, avoid["active"]),
            "horizon": "5-20 trading days",
        },
        "long_term": {
            "score": long_score,
            "view": _view(long_score, avoid["active"] and long_score < 50),
            "horizon": "6-18 months",
        },
        "avoid": avoid,
        "technical": technical,
        "strategy": strategy,
        "news": news,
        "quant_score": stock.get("total_score"),
        "risk_adjusted_score": stock.get("risk_adjusted_score"),
    }


def _short_term_score(stock: Dict[str, Any], technical: Dict[str, Any]) -> float:
    score = float(technical.get("technical_score") or 0) * 0.55
    price = technical.get("price") or 0
    ema9, ema21, ema50 = technical.get("ema_9"), technical.get("ema_21"), technical.get("ema_50")
    if ema9 and ema21 and ema50:
        score += 15 if ema9 > ema21 > ema50 else 5 if ema9 > ema21 else 0
    adx = technical.get("adx_14")
    if adx is not None:
        score += 10 if adx >= 25 else 5 if adx >= 18 else 0
    if ema21 and price > ema21:
        score += 10
    penalty = float(stock.get("risk_penalty") or 0)
    score += max(0, 10 - penalty)
    return round(max(0, min(100, score)), 1)


def _long_term_score(stock: Dict[str, Any], technical: Dict[str, Any]) -> float:
    fundamental = float(stock.get("growth_score") or 0)
    price = technical.get("price") or 0
    sma200 = technical.get("sma_200")
    ema200 = technical.get("ema_200")
    trend = 0.0
    if sma200 and price > sma200:
        trend += 10
    if ema200 and price > ema200:
        trend += 10
    penalty = float(stock.get("risk_penalty") or 0)
    return round(max(0, min(100, fundamental * 0.8 + trend - penalty * 0.5)), 1)


def _avoid_assessment(
    stock: Dict[str, Any], technical: Dict[str, Any], short_score: float, long_score: float,
) -> Dict[str, Any]:
    reasons = []
    price = technical.get("price") or 0
    sma50, sma200 = technical.get("sma_50"), technical.get("sma_200")
    if short_score < 45 and long_score < 50:
        reasons.append("Weak short- and long-horizon scores")
    if sma50 and sma200 and price < sma50 < sma200:
        reasons.append("Price is below both SMA50 and SMA200")
    if stock.get("risk_penalty_level") == "high":
        reasons.append("High volatility or drawdown risk")
    if stock.get("metrics_used", 0) < 4:
        reasons.append("Insufficient fundamental coverage")
    return {
        "active": bool(reasons),
        "reasons": reasons,
        "review": "Review after 5 trading days or a material signal change",
        "invalidation": "Avoid status clears when risk and trend conditions recover",
    }


def _view(score: float, avoid: bool) -> str:
    if avoid:
        return "avoid"
    if score >= 70:
        return "bullish"
    if score >= 50:
        return "neutral"
    return "avoid"
