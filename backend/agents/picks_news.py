from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agents.data_fetcher import fetch_news, fetch_next_earnings
from agents.llm_agent import analyze_news_impact
from utils.cache import cache


def analyze_picks_news(
    tickers: List[str],
    lang: str = "zh_tw",
    force_refresh: bool = False,
    include_ai: bool = True,
    max_items: int = 8,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    results = {}
    for index, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(ticker, index, len(tickers))
        try:
            results[ticker] = analyze_ticker_news(ticker, lang, force_refresh, include_ai, max_items)
        except Exception as exc:
            results[ticker] = {"ticker": ticker, "status": "error", "items": [], "errors": {"unexpected": str(exc)}}
    return results


def analyze_ticker_news(
    ticker: str,
    lang: str = "zh_tw",
    force_refresh: bool = False,
    include_ai: bool = True,
    max_items: int = 8,
) -> Dict[str, Any]:
    errors: Dict[str, Optional[str]] = {"news": None, "earnings": None, "ai": None}
    try:
        items = fetch_news(ticker, max_items=max_items, force_refresh=force_refresh)
    except Exception as exc:
        items = []
        errors["news"] = str(exc)
    try:
        earnings = fetch_next_earnings(ticker, force_refresh=force_refresh)
        if not earnings.get("available") and (earnings.get("calendar_error") or earnings.get("fallback_error")):
            errors["earnings"] = earnings.get("fallback_error") or earnings.get("calendar_error")
    except Exception as exc:
        earnings = {"available": False}
        errors["earnings"] = str(exc)

    enriched = []
    ai_failures = []
    for article in items:
        item = dict(article)
        if include_ai:
            impact_key = f"news_impact_v1_{ticker}_{item.get('id', '')}_{lang}"
            impact = None if force_refresh else cache.get(impact_key, "info", ttl=21600)
            if impact is None:
                impact = analyze_news_impact(ticker, item, earnings=earnings, lang=lang)
                if not impact.get("error"):
                    cache.set(impact_key, "info", impact, ttl=21600)
            if impact.get("error"):
                ai_failures.append(impact["error"])
                impact = _fallback_impact(item, lang)
                item["analysis_source"] = "rules"
            else:
                item["analysis_source"] = "ai"
            item["impact"] = impact
        else:
            item["impact"] = _fallback_impact(item, lang)
            item["analysis_source"] = "rules"
        enriched.append(item)
    if ai_failures:
        errors["ai"] = ai_failures[0]
    status = "error" if not enriched and errors["news"] else "partial" if any(errors.values()) else "ok"
    return {
        "ticker": ticker,
        "items": enriched,
        "earnings": earnings,
        "status": status,
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fallback_impact(article: Dict[str, Any], lang: str) -> Dict[str, Any]:
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    event_rules = {
        "earnings": ("earnings", "revenue", "eps", "quarter", "results"),
        "guidance": ("guidance", "outlook", "forecast"),
        "product": ("launch", "product", "approval", "patent"),
        "analyst_action": ("upgrade", "downgrade", "price target", "analyst"),
        "regulatory": ("regulator", "regulatory", "antitrust", "investigation", "probe"),
        "litigation": ("lawsuit", "court", "settlement", "legal"),
        "m_and_a": ("acquisition", "acquire", "merger", "takeover"),
        "management": ("ceo", "cfo", "executive", "resign"),
        "macro": ("fed", "interest rate", "tariff", "inflation", "economy"),
    }
    event_type = next((kind for kind, words in event_rules.items() if any(word in text for word in words)), "other")
    sentiment = article.get("sentiment", "neutral")
    thesis = {
        "zh_cn": "基于标题和摘要的规则分析；需要结合正式公告、市场预期和价格反应确认。",
        "zh_tw": "基於標題與摘要的規則分析；需要結合正式公告、市場預期和價格反應確認。",
        "en": "Rule-based analysis from the headline and summary; confirm against the official release, expectations, and price reaction.",
    }.get(lang, "Rule-based analysis from the headline and summary.")
    return {
        "direction": sentiment if sentiment in {"positive", "neutral", "negative"} else "neutral",
        "magnitude": "medium" if event_type in {"earnings", "guidance", "regulatory", "litigation", "m_and_a"} else "low",
        "horizon": "short_term",
        "event_type": event_type,
        "thesis": thesis,
        "key_risks": [],
        "key_catalysts": [],
        "confidence": 35,
    }
