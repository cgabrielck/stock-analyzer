import concurrent.futures
import queue
import time
from typing import Any, Callable, Dict, List, Optional

from agents.data_fetcher import (
    fetch_news,
    fetch_options_chain,
    fetch_stock_data,
    fetch_trading_session_ranges,
)
from agents.fundamental_analyzer import calculate_growth_score
from agents.llm_agent import suggest_trading_strategy
from agents.risk_analyzer import calculate_risk_adjusted_score
from agents.technical_analyzer import compute_technical_indicators
from utils.constants import STOCK_UNIVERSE


ProgressCallback = Callable[[Dict[str, Any]], None]


def analyze_ticker(
    ticker: str,
    lang: str = "zh_tw",
    force_refresh: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    _emit(progress_callback, ticker, "fundamental", "started")
    stock = fetch_stock_data(ticker, force_refresh=force_refresh)
    if stock.get("error"):
        _emit(progress_callback, ticker, "fundamental", "failed")
        return {"ticker": ticker, "error": stock["error"], "stage": "fundamental"}
    _emit(progress_callback, ticker, "fundamental", "completed")

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
    _emit(progress_callback, ticker, "technical", "started")
    technical = compute_technical_indicators(ticker, period="1y", force_refresh=force_refresh)
    if technical.get("error"):
        _emit(progress_callback, ticker, "technical", "failed")
        return {"ticker": ticker, "error": technical["error"], "stage": "technical"}
    _emit(progress_callback, ticker, "technical", "completed")

    technical_score = technical.get("technical_score")
    if technical_score is not None:
        stock["technical_score"] = technical_score
        stock["total_score"] = round(growth_score * 0.7 + technical_score * 0.3, 1)
    stock["risk_metrics"] = technical.get("risk_metrics", {"available": False})
    stock.update(calculate_risk_adjusted_score(stock["total_score"], stock["risk_metrics"]))
    return analyze_selected_stock(stock, lang=lang, technical=technical, progress_callback=progress_callback)


def analyze_tickers(
    tickers: List[str],
    lang: str = "zh_tw",
    force_refresh: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Dict[str, Any]]:
    unordered: Dict[str, Dict[str, Any]] = {}
    events: queue.Queue[Dict[str, Any]] = queue.Queue()

    def analyze(ticker: str) -> Dict[str, Any]:
        try:
            return analyze_ticker(ticker, lang=lang, force_refresh=force_refresh, progress_callback=events.put)
        except Exception as exc:
            return {"ticker": ticker, "error": str(exc), "stage": "unexpected"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(tickers) or 1)) as executor:
        futures = {executor.submit(analyze, ticker): ticker for ticker in tickers}
        pending = set(futures)
        while pending:
            try:
                event = events.get(timeout=0.2)
                _safe_callback(progress_callback, event)
            except queue.Empty:
                _safe_callback(progress_callback, {"ticker": None, "stage": "heartbeat", "state": "running"})
            completed = {future for future in pending if future.done()}
            for future in completed:
                ticker = futures[future]
                while not events.empty():
                    _safe_callback(progress_callback, events.get_nowait())
                unordered[ticker] = future.result()
                _safe_callback(progress_callback, {"ticker": ticker, "stage": "ticker", "state": "completed"})
            pending -= completed
        while not events.empty():
            _safe_callback(progress_callback, events.get_nowait())
    return {ticker: unordered[ticker] for ticker in tickers}


def analyze_selected_stock(
    stock: Dict[str, Any], lang: str = "zh_tw", technical: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    ticker = stock["ticker"]
    technical = technical or compute_technical_indicators(ticker, period="1y", force_refresh=False)
    if technical.get("error"):
        return {"ticker": ticker, "error": technical["error"]}

    short_score = _short_term_score(stock, technical)
    long_score = _long_term_score(stock, technical)
    avoid = _avoid_assessment(stock, technical, short_score, long_score)
    trade_plan = _build_trade_plan(stock, technical, short_score, long_score, avoid)
    current_price = technical.get("price") or stock.get("price") or 0
    _emit(progress_callback, ticker, "market_data", "started")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        options_future = executor.submit(fetch_options_chain, ticker, current_price=current_price)
        sessions_future = executor.submit(fetch_trading_session_ranges, ticker)
        news_future = executor.submit(fetch_news, ticker, 5)
        options = options_future.result()
        session_ranges = sessions_future.result()
        news = news_future.result()
    options_plan = _build_options_plan(options, trade_plan)
    _emit(progress_callback, ticker, "market_data", "completed")
    _emit(progress_callback, ticker, "strategy", "started")
    strategy = suggest_trading_strategy(
        ticker,
        stock,
        technical,
        current_price,
        options_data=options,
        news_data=news,
        lang=lang,
    )
    _emit(progress_callback, ticker, "strategy", "failed" if strategy.get("error") else "completed")
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
        "trade_plan": trade_plan,
        "options": options,
        "options_plan": options_plan,
        "session_ranges": session_ranges,
        "validation": {"available": False, "reason": "not_run"},
        "news": news,
        "quant_score": stock.get("total_score"),
        "risk_adjusted_score": stock.get("risk_adjusted_score"),
    }


def _emit(callback: Optional[ProgressCallback], ticker: str, stage: str, state: str) -> None:
    _safe_callback(callback, {"ticker": ticker, "stage": stage, "state": state, "timestamp": time.monotonic()})


def _safe_callback(callback: Optional[ProgressCallback], event: Dict[str, Any]) -> None:
    if callback:
        try:
            callback(event)
        except Exception:
            pass


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


def _build_trade_plan(
    stock: Dict[str, Any],
    technical: Dict[str, Any],
    short_score: float,
    long_score: float,
    avoid: Dict[str, Any],
) -> Dict[str, Any]:
    price = float(technical.get("price") or stock.get("price") or 0)
    if price <= 0:
        return {"action": "no_trade", "error": "price_unavailable"}
    atr = float(technical.get("atr_14") or price * 0.025)
    bb_lower = technical.get("bb_lower")
    bb_upper = technical.get("bb_upper")
    ema21 = technical.get("ema_21")
    sma50 = technical.get("sma_50")
    bullish = short_score >= 60 and not avoid.get("active")
    bearish = short_score < 45 or (avoid.get("active") and long_score < 50)
    if bullish:
        stance, action, setup = "bullish", "buy", "pullback_or_breakout"
        support_candidates = [value for value in (ema21, sma50, bb_lower) if value and value < price]
        support = max(support_candidates) if support_candidates else price - atr
        entry_low = max(support, price - 0.75 * atr)
        entry_high = price + 0.15 * atr
        stop = min(entry_low - 0.8 * atr, support - 0.35 * atr)
        risk = max(entry_high - stop, atr)
        targets = [entry_high + 1.5 * risk, entry_high + 2.5 * risk]
        confirmation = max(price + 0.25 * atr, float(bb_upper or 0))
        execution = "Regular session; use a limit order after the first 15 minutes"
    elif bearish:
        stance, action, setup = "bearish", "avoid_or_hedge", "failed_rally_or_breakdown"
        resistance_candidates = [value for value in (ema21, sma50, bb_upper) if value and value > price]
        resistance = min(resistance_candidates) if resistance_candidates else price + atr
        entry_low = price - 0.15 * atr
        entry_high = min(resistance, price + 0.75 * atr)
        stop = max(entry_high + 0.8 * atr, resistance + 0.35 * atr)
        risk = max(stop - entry_low, atr)
        targets = [max(0.01, entry_low - 1.5 * risk), max(0.01, entry_low - 2.5 * risk)]
        confirmation = max(0.01, min(price - 0.25 * atr, float(bb_lower or price)))
        execution = "Regular session; wait for a failed rally or confirmed breakdown"
    else:
        stance, action, setup = "neutral", "watch", "wait_for_confirmation"
        entry_low, entry_high = price - 0.5 * atr, price + 0.5 * atr
        stop, risk = price - 1.5 * atr, 1.5 * atr
        targets = [price + 1.5 * atr, price + 2.5 * atr]
        confirmation = price + atr
        execution = "No immediate entry; reassess during regular-session liquidity"
    return {
        "stance": stance,
        "action": action,
        "setup": setup,
        "execution_window": execution,
        "entry_zone": {"low": round(entry_low, 2), "high": round(entry_high, 2)},
        "confirmation_price": round(confirmation, 2),
        "stop_loss": round(stop, 2),
        "targets": [round(value, 2) for value in targets],
        "risk_reward": [1.5, 2.5],
        "atr_14": round(atr, 2),
        "method": "Deterministic ATR and observed support/resistance levels",
    }


def _build_options_plan(options: Dict[str, Any], trade_plan: Dict[str, Any]) -> Dict[str, Any]:
    stance = trade_plan.get("stance")
    if options.get("error") or stance not in {"bullish", "bearish"}:
        return {"action": "none", "reason": options.get("error") or "No directional edge"}
    option_type = "call" if stance == "bullish" else "put"
    candidates = options.get("calls" if option_type == "call" else "puts", [])
    liquid = [
        contract for contract in candidates
        if contract.get("ask") and contract.get("ask") > 0
        and contract.get("bid") is not None
        and (contract.get("open_interest", 0) >= 100 or contract.get("volume", 0) >= 25)
        and (contract.get("spread_pct") is None or contract["spread_pct"] <= 20)
    ]
    if not liquid:
        return {"action": "none", "reason": "No sufficiently liquid near-the-money contract"}
    contract = liquid[0]
    entry = contract.get("mid") or contract.get("ask")
    if not entry:
        return {"action": "none", "reason": "Option premium unavailable"}
    return {
        "action": "buy_to_open",
        "option_type": option_type,
        "expiry": options.get("selected_expiry") or options.get("nearest_expiry"),
        "contract": contract,
        "max_entry_premium": round(min(float(contract["ask"]), float(entry) * 1.05), 2),
        "stop_premium": round(float(entry) * 0.65, 2),
        "take_profit_premiums": [round(float(entry) * 1.35, 2), round(float(entry) * 1.7, 2)],
        "exit_rule": "Scale out at +35% and +70%; exit before expiry or on underlying invalidation",
        "underlying_invalidation": trade_plan.get("stop_loss"),
        "max_position_risk_pct": 1.0,
        "method": "Nearest liquid near-the-money contract with at least 21 DTE when available",
    }
