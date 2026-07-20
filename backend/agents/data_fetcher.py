import concurrent.futures
import json
import os
from typing import Any, Callable, Dict, Optional

import yfinance as yf
import requests

from utils.constants import STOCK_UNIVERSE, SEC_HEADERS, DATA_DIR
from utils.cache import cache
from utils.price_utils import get_latest_price
from agents.auto_upgrader import agent_state
from agents.sec_analyzer import ticker_to_cik
try:
    from agents.china_data_fetcher import fetch_china_data, fetch_china_daily
except ImportError:
    fetch_china_data = None
    fetch_china_daily = None

_REQUEST_SESSION: requests.Session = requests.Session()
_REQUEST_SESSION.headers.update(SEC_HEADERS)
_REQUEST_SESSION.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "KHTML, like Gecko Chrome/120.0.0.0 Safari/537.36"
)

try:
    from yfinance.utils import YfConfig
    YfConfig.session = _REQUEST_SESSION
except Exception:
    pass

_SEED_DATA: Dict[str, Any] = {}
try:
    from agents.seed_data import SEED_DATA as _SD
    _SEED_DATA = _SD
except Exception:
    _seed_path = os.path.join(DATA_DIR, "seed_data.json")
    if os.path.exists(_seed_path):
        try:
            with open(_seed_path) as _f:
                _SEED_DATA = json.load(_f)
        except Exception:
            pass

REQUEST_TIMEOUT: int = 30
MAX_WORKERS: int = 3


import time as _time


def _now_str() -> str:
    return _time.strftime("%Y-%m-%d %H:%M:%S")


SCORING_KEYS: list[str] = ["revenue_growth", "eps_growth", "profit_margin", "peg", "roe", "debt_equity"]


def _count_available_metrics(data: Dict[str, Any]) -> int:
    return sum(1 for k in SCORING_KEYS if data.get(k) is not None and data.get(k) != 0)


def fetch_stock_data(ticker: str) -> Dict[str, Any]:
    cached = cache.get(ticker, "info")
    if cached:
        cached["data_quality"] = {
            "from_cache": True,
            "fetched_at": cached.get("fetched_at", "unknown"),
            "metrics_available": _count_available_metrics(cached),
            "metrics_total": len(SCORING_KEYS),
        }
        return cached

    last_error: Optional[str] = None

    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker, session=_REQUEST_SESSION)
            info = stock.info
            if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
                price_data = _fetch_price_fallback(ticker)
                if price_data:
                    info.update(price_data)

            financials = _safe_df(stock.financials)
            balance_sheet = _safe_df(stock.balance_sheet)
            cashflow = _safe_df(stock.cashflow)

            cik = info.get("cik")
            if cik is None:
                cik = ticker_to_cik(ticker)

            recommendation_mean = info.get("recommendationMean")
            if recommendation_mean is not None:
                rating_map = {1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Underperform", 5: "Sell"}
                rating_label = rating_map.get(round(recommendation_mean), "N/A")
            else:
                rating_label = None

            latest_price, price_session = get_latest_price(stock)

            result: Dict[str, Any] = {
                "ticker": ticker,
                "fetched_at": _now_str(),
                "price": latest_price,
                "price_session": price_session,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector") or next(
                    (s["sector"] for s in STOCK_UNIVERSE if s["ticker"] == ticker), None
                ),
                "industry": info.get("industry"),
                "longName": info.get("longName"),
                "cik": cik,
                "peg": info.get("pegRatio"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "pb_ratio": info.get("priceToBook"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "dividend_yield": info.get("dividendYield"),
                "short_ratio": info.get("shortRatio"),
                "beta": info.get("beta"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "target_mean_price": info.get("targetMeanPrice"),
                "target_high_price": info.get("targetHighPrice"),
                "target_low_price": info.get("targetLowPrice"),
                "recommendation_mean": recommendation_mean,
                "rating_label": rating_label,
                "number_of_analysts": info.get("numberOfAnalystOpinions"),
                "held_percent_institutions": info.get("heldPercentInstitutions"),
            }

            if financials is not None:
                result.update(_extract_financials(financials, balance_sheet, cashflow))

            try:
                esg_data = stock.sustainability
                if esg_data is not None and not esg_data.empty:
                    result["esg_score"] = float(esg_data.loc["totalEsg", "realValue"]) if "totalEsg" in esg_data.index else None
            except Exception as e:
                agent_state.log_source_result(f"esg:{ticker}", False, str(e))

            try:
                insider = stock.insider_transactions
                if insider is not None and not insider.empty:
                    net = insider["shares"].sum() if "shares" in insider.columns else 0
                    result["insider_net_shares"] = int(net)
            except Exception as e:
                agent_state.log_source_result(f"insider:{ticker}", False, str(e))

            result["data_quality"] = {
                "from_cache": False,
                "fetched_at": result["fetched_at"],
                "metrics_available": _count_available_metrics(result),
                "metrics_total": len(SCORING_KEYS),
            }

            agent_state.log_source_result(f"yfinance:{ticker}", True)
            cache.set(ticker, "info", result)
            return result

        except Exception as e:
            last_error = str(e)
            agent_state.log_source_result(f"yfinance:{ticker}", False, last_error)
            if attempt < 2:
                _time.sleep(2 ** attempt)

    china = fetch_china_data(ticker) if fetch_china_data else None
    if china:
        china["sector"] = next(
            (s["sector"] for s in STOCK_UNIVERSE if s["ticker"] == ticker), None
        )
        china["cik"] = ticker_to_cik(ticker)
        china["fetched_at"] = _now_str()
        china["data_quality"] = {
            "from_cache": False,
            "fetched_at": china["fetched_at"],
            "metrics_available": _count_available_metrics(china),
            "metrics_total": len(SCORING_KEYS),
        }
        seed = _SEED_DATA.get(ticker)
        if seed:
            for k in ("revenue_growth", "eps_growth", "profit_margin", "peg",
                      "roe", "debt_equity", "revenue_ttm", "net_income",
                      "net_income_growth", "eps", "beta", "dividend_yield",
                      "target_mean_price", "fifty_two_week_high",
                      "fifty_two_week_low", "longName", "insider_net_shares",
                      "esg_score", "recommendation_mean", "rating_label",
                      "number_of_analysts", "held_percent_institutions",
                      "ps_ratio", "pb_ratio", "ev_ebitda", "short_ratio",
                      "target_high_price", "target_low_price", "forward_pe"):
                if k not in china and k in seed:
                    china[k] = seed[k]
        agent_state.log_source_result(f"china:{ticker}", True)
        return china

    fallback = _fetch_price_fallback(ticker)
    if fallback:
        cik = ticker_to_cik(ticker)
        fallback["ticker"] = ticker
        fallback["cik"] = cik
        fallback["fetched_at"] = _now_str()
        fallback["sector"] = next(
            (s["sector"] for s in STOCK_UNIVERSE if s["ticker"] == ticker), None
        )
        seed = _SEED_DATA.get(ticker)
        if seed:
            for k in ("revenue_growth", "eps_growth", "profit_margin", "peg",
                      "roe", "debt_equity", "longName"):
                if k not in fallback and k in seed:
                    fallback[k] = seed[k]
        agent_state.log_source_result(f"fallback:{ticker}", True)
        return fallback

    seed = _SEED_DATA.get(ticker)
    if seed:
        seed["fetched_at"] = _now_str()
        agent_state.log_source_result(f"seed:{ticker}", True)
        return seed

    return {"ticker": ticker, "error": last_error or "unknown", "sector": None}


def _safe_df(df: Any) -> Optional[Any]:
    if df is None or df.empty:
        return None
    return df


def _extract_financials(financials: Any, balance_sheet: Any, cashflow: Any) -> Dict[str, float]:
    result: Dict[str, float] = {}
    try:
        if "Total Revenue" in financials.index:
            rev = financials.loc["Total Revenue"].dropna()
            if len(rev) >= 2:
                result["revenue_growth"] = float((rev.iloc[0] / rev.iloc[1] - 1) * 100)
            if len(rev) >= 1:
                result["revenue_ttm"] = float(rev.iloc[0])
    except Exception:
        pass

    try:
        if "Net Income" in financials.index:
            ni = financials.loc["Net Income"].dropna()
            if len(ni) >= 1:
                result["net_income"] = float(ni.iloc[0])
            if len(ni) >= 2:
                result["net_income_growth"] = float((ni.iloc[0] / ni.iloc[1] - 1) * 100)
    except Exception:
        pass

    try:
        if "Total Revenue" in financials.index and "Net Income" in financials.index:
            rev = financials.loc["Total Revenue"].dropna()
            ni = financials.loc["Net Income"].dropna()
            if len(rev) >= 1 and len(ni) >= 1 and rev.iloc[0] != 0:
                result["profit_margin"] = float((ni.iloc[0] / rev.iloc[0]) * 100)
    except Exception:
        pass

    try:
        if balance_sheet is not None and "Total Debt" in balance_sheet.index and "Stockholders Equity" in balance_sheet.index:
            debt = balance_sheet.loc["Total Debt"].dropna()
            equity = balance_sheet.loc["Stockholders Equity"].dropna()
            if len(debt) >= 1 and len(equity) >= 1 and equity.iloc[0] != 0:
                result["debt_equity"] = float(debt.iloc[0] / equity.iloc[0])
    except Exception:
        pass

    try:
        if "Net Income" in financials.index and balance_sheet is not None and "Stockholders Equity" in balance_sheet.index:
            ni = financials.loc["Net Income"].dropna()
            equity = balance_sheet.loc["Stockholders Equity"].dropna()
            if len(ni) >= 1 and len(equity) >= 1 and equity.iloc[0] != 0:
                result["roe"] = float((ni.iloc[0] / equity.iloc[0]) * 100)
    except Exception:
        pass

    try:
        if cashflow is not None and "Free Cash Flow" in cashflow.index:
            fcf = cashflow.loc["Free Cash Flow"].dropna()
            if len(fcf) >= 1:
                result["fcf"] = float(fcf.iloc[0])
    except Exception:
        pass

    try:
        if "Diluted EPS" in financials.index:
            eps = financials.loc["Diluted EPS"].dropna()
            if len(eps) >= 2:
                result["eps_growth"] = float((eps.iloc[0] / eps.iloc[1] - 1) * 100)
    except Exception:
        pass

    return result


def _fetch_price_fallback(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        resp = _REQUEST_SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if price:
            return {"price": price, "sector": None, "_fallback": True}
    except Exception:
        pass
    return None


def fetch_all_stocks(
    selected_tickers: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    tickers = selected_tickers or [s["ticker"] for s in STOCK_UNIVERSE]
    results: Dict[str, Dict[str, Any]] = {}
    completed = 0
    total = len(tickers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(fetch_stock_data, t): t for t in tickers}
        for future in concurrent.futures.as_completed(future_map):
            ticker = future_map[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                results[ticker] = {"ticker": ticker, "error": str(e)}
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return results


_POSITIVE_KEYWORDS: set[str] = {
    "beat", "surge", "surges", "surged", "growth", "upgrade", "upgraded",
    "launch", "launched", "record", "positive", "partnership", "strong",
    "rally", "gain", "gains", "bull", "bullish", "raised", "exceed",
    "outperform", "innovation", "milestone", "soar", "soars", "boom",
    "expands", "expansion", "profit", "profitable", "momentum",
}

_NEGATIVE_KEYWORDS: set[str] = {
    "drop", "drops", "dropped", "miss", "missed", "downgrade", "downgraded",
    "lawsuit", "investigation", "layoff", "layoffs", "recall", "loss",
    "decline", "declines", "fall", "falls", "fell", "cut", "sell",
    "bear", "bearish", "warning", "risk", "regulatory", "fine", "fined",
    "probe", "scrutiny", "slowdown", "weak", "weakness", "struggle",
    "volatile", "uncertainty", "penalty",
}


def _analyze_news_sentiment(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    pos_count = sum(1 for kw in _POSITIVE_KEYWORDS if kw in text)
    neg_count = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in text)
    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def _extract_news(item: dict) -> dict:
    content = item.get("content") or item
    title = content.get("title", "")
    summary = (content.get("summary", "") or content.get("description", ""))
    publisher = ""
    provider = content.get("provider")
    if provider:
        publisher = provider.get("displayName", "") or provider.get("name", "")
    link = ""
    canonical = content.get("canonicalUrl")
    if canonical:
        link = canonical.get("url", "")
    if not link:
        click = content.get("clickThroughUrl")
        if click:
            link = click.get("url", "")
    return {"title": title, "summary": summary, "publisher": publisher, "link": link}


def fetch_news(ticker: str, max_items: int = 5) -> list[dict[str, Any]]:
    cached = cache.get(f"news_{ticker}", "info")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker, session=_REQUEST_SESSION)
        raw_news = stock.news
        if not raw_news:
            return []
    except Exception as e:
        agent_state.log_source_result(f"news:{ticker}", False, str(e))
        return []

    result: list[dict[str, Any]] = []
    for item in raw_news[:max_items]:
        parsed = _extract_news(item)
        title = parsed["title"]
        summary = parsed["summary"]
        sentiment = _analyze_news_sentiment(title, summary)
        result.append({
            "ticker": ticker,
            "title": title,
            "summary": summary[:300],
            "publisher": parsed["publisher"],
            "link": parsed["link"],
            "sentiment": sentiment,
        })

    agent_state.log_source_result(f"news:{ticker}", True)
    cache.set(f"news_{ticker}", "info", result)
    return result


def fetch_financials_history(ticker: str) -> dict[str, list[float]]:
    cached = cache.get(f"hist_{ticker}", "financials")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker, session=_REQUEST_SESSION)
        fin = stock.financials
        if fin is None or fin.empty:
            return {}
    except Exception:
        return {}

    result: dict[str, list[float]] = {}
    try:
        if "Total Revenue" in fin.index:
            rev = fin.loc["Total Revenue"].dropna().tolist()
            result["revenue"] = [float(v) for v in rev[:5]]
    except Exception:
        pass
    try:
        if "Net Income" in fin.index:
            ni = fin.loc["Net Income"].dropna().tolist()
            result["net_income"] = [float(v) for v in ni[:5]]
    except Exception:
        pass
    try:
        if "Diluted EPS" in fin.index:
            eps = fin.loc["Diluted EPS"].dropna().tolist()
            result["eps"] = [float(v) for v in eps[:5]]
    except Exception:
        pass

    if result:
        cache.set(f"hist_{ticker}", "financials", result)
    return result


def fetch_options_chain(ticker: str) -> Dict[str, Any]:
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return {"error": "no_options"}
        nearest = expirations[0]
        chain = stock.option_chain(nearest)
        calls = chain.calls
        puts = chain.puts
        if calls.empty and puts.empty:
            return {"error": "empty_chain"}
        atm_strike = None
        spot = get_latest_price(stock)[0]
        if spot:
            if not calls.empty:
                idx = (calls["strike"] - spot).abs().idxmin()
                atm_strike = float(calls.loc[idx, "strike"])
            elif not puts.empty:
                idx = (puts["strike"] - spot).abs().idxmin()
                atm_strike = float(puts.loc[idx, "strike"])
        return {
            "ticker": ticker,
            "expirations": list(expirations),
            "nearest_expiry": nearest,
            "num_calls": len(calls),
            "num_puts": len(puts),
            "atm_strike": atm_strike,
            "max_call_oi": float(calls.loc[calls["openInterest"].idxmax(), "strike"]) if not calls.empty and calls["openInterest"].max() > 0 else None,
            "max_put_oi": float(puts.loc[puts["openInterest"].idxmax(), "strike"]) if not puts.empty and puts["openInterest"].max() > 0 else None,
            "max_call_volume": float(calls.loc[calls["volume"].idxmax(), "strike"]) if not calls.empty and calls["volume"].max() > 0 else None,
            "max_put_volume": float(puts.loc[puts["volume"].idxmax(), "strike"]) if not puts.empty and puts["volume"].max() > 0 else None,
            "put_call_ratio": len(puts) / len(calls) if len(calls) > 0 else None,
        }
    except Exception as e:
        return {"error": str(e)}


def suggest_options_fallback(ticker: str, technical_data: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    opt = fetch_options_chain(ticker)
    if "error" in opt:
        return {"error": opt["error"], "option_type": "none"}
    rsi = technical_data.get("rsi_14")
    macd_hist = technical_data.get("macd_histogram")
    bb_signal = technical_data.get("bb_signal")
    trend = technical_data.get("trend_signal")
    support = technical_data.get("bb_lower") or current_price * 0.9
    resistance = technical_data.get("bb_upper") or current_price * 1.1
    option_type = "none"
    if trend == "uptrend" and rsi and rsi < 65:
        option_type = "call"
    elif trend == "downtrend" and rsi and rsi > 35:
        option_type = "put"
    elif rsi and rsi >= 70:
        option_type = "put"
    elif rsi and rsi <= 30:
        option_type = "call"
    strike = opt.get("atm_strike")
    if strike is None:
        strike = round(current_price, 0)
    expiry = opt.get("nearest_expiry", "next monthly")
    return {
        "option_type": option_type,
        "strike_price": strike,
        "expiration": expiry,
        "key_support": round(support, 2) if support else None,
        "key_resistance": round(resistance, 2) if resistance else None,
        "reasoning": "",
    }


INDUSTRY_NEWS_SOURCES: Dict[str, str] = {
    "Semiconductors": "SMH",
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial": "XLF",
    "Consumer": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Space": "ARKX",
    "Memory & Storage": "SMH",
    "Defense & Aerospace": "ITA",
}

_CLIMATE_KEYWORDS = [
    "climate", "warming", "carbon", "emission", "renewable", "solar", "wind",
    "green energy", "clean energy", "net zero", "global warming", "weather",
    "heat wave", "flood", "drought", "wildfire", "hurricane", "COP",
    "environmental", "ESG", "sustainable", "fossil fuel", "pollution",
]


def _is_climate_related(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in _CLIMATE_KEYWORDS)


def fetch_industry_news(
    max_per_source: int = 3,
    max_total: int = 20,
) -> Dict[str, Any]:
    cached = cache.get("industry_news", "info")
    if cached:
        return cached

    result: Dict[str, Any] = {
        "by_sector": {},
        "climate_items": [],
        "all_headlines": [],
    }

    for sector_name, etf_ticker in INDUSTRY_NEWS_SOURCES.items():
        try:
            stock = yf.Ticker(etf_ticker, session=_REQUEST_SESSION)
            raw = stock.news
            if not raw:
                continue
            sector_news: list[Dict[str, Any]] = []
            for item in raw[:max_per_source]:
                parsed = _extract_news(item)
                title = parsed["title"]
                summary = parsed["summary"]
                entry = {
                    "title": title,
                    "summary": summary[:300],
                    "publisher": parsed["publisher"],
                    "link": parsed["link"],
                    "sector": sector_name,
                }
                sector_news.append(entry)
                result["all_headlines"].append(dict(entry))
                if _is_climate_related(title, summary):
                    result["climate_items"].append(dict(entry))
            if sector_news:
                result["by_sector"][sector_name] = sector_news
        except Exception:
            pass

    result["all_headlines"] = result["all_headlines"][:max_total]
    agent_state.log_source_result("industry_news", bool(result["all_headlines"]),
                                  "" if result["all_headlines"] else "no news")
    cache.set("industry_news", "info", result)
    return result


def suggest_price_fallback(ticker: str, technical_data: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    bb_upper = technical_data.get("bb_upper")
    bb_lower = technical_data.get("bb_lower")
    sma20 = technical_data.get("sma_20")
    sma50 = technical_data.get("sma_50")
    rsi = technical_data.get("rsi_14")
    buy = None
    sell = None
    stop = None
    confidence = 50
    if rsi is not None:
        if rsi >= 70:
            confidence = 65
            sell = round(current_price * 1.05, 2) if bb_upper else round(current_price * 1.03, 2)
            stop = round(current_price * 0.95, 2)
        elif rsi <= 30:
            confidence = 65
            buy = round(current_price, 2)
            sell = round(current_price * 1.10, 2) if bb_upper else round(current_price * 1.05, 2)
            stop = round(current_price * 0.93, 2)
        else:
            confidence = 50
            buy = round(current_price * 0.97, 2) if sma20 else None
            sell = round(bb_upper, 2) if bb_upper else round(current_price * 1.05, 2)
            stop = round(sma50 or current_price * 0.92, 2)
    return {
        "buy_price": buy,
        "sell_price": sell,
        "stop_loss": stop,
        "confidence": confidence,
        "reasoning": "",
    }
