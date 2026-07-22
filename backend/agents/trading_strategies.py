from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import yfinance as yf
import numpy as np

from utils.cache import cache
from agents.data_fetcher import fetch_options_chain
from agents.auto_upgrader import agent_state

# --- Configurable thresholds ---
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VOLUME_SPIKE_RATIO = 1.5
ATR_STOP_MULTIPLIER = 2.5
TREND_CONFIRM_WINDOW = 10
MAX_CONSECUTIVE_LOSSES = 3
MIN_RISK_REWARD = 1.5

SECTOR_ETF_MAP = {
    "Semiconductors": "SMH", "Technology": "XLK", "Healthcare": "XLV",
    "Financial": "XLF", "Consumer": "XLY", "Energy": "XLE",
    "Industrials": "XLI", "Space": None, "Memory & Storage": None,
    "Defense & Aerospace": "ITA",
}

STRATEGIES = [
    {
        "id": "trend_following",
        "name_key": "strategy.trend_following",
        "time_horizon": "Swing / Position",
        "difficulty_key": "strategy.diff_beginner",
        "suitable_regime": ["bullish"],
        "order": 1,
    },
    {
        "id": "mean_reversion",
        "name_key": "strategy.mean_reversion",
        "time_horizon": "Swing",
        "difficulty_key": "strategy.diff_intermediate",
        "suitable_regime": ["sideways"],
        "order": 2,
    },
    {
        "id": "breakout_momentum",
        "name_key": "strategy.breakout_momentum",
        "time_horizon": "Swing",
        "difficulty_key": "strategy.diff_intermediate",
        "suitable_regime": ["bullish", "volatile"],
        "order": 3,
    },
    {
        "id": "value_entry",
        "name_key": "strategy.value_entry",
        "time_horizon": "Position / Long-term",
        "difficulty_key": "strategy.diff_beginner",
        "suitable_regime": ["any"],
        "order": 4,
    },
    {
        "id": "income_defensive",
        "name_key": "strategy.income_defensive",
        "time_horizon": "Long-term",
        "difficulty_key": "strategy.diff_beginner",
        "suitable_regime": ["any"],
        "order": 5,
    },
]


def _get_stock(ticker: str):
    return yf.Ticker(ticker)


def detect_market_regime(ticker: str) -> Dict[str, str]:
    cached = cache.get(f"mkt_regime_{ticker}", "strategy")
    if cached:
        return cached
    result = {"trend": "sideways", "volatility": "normal"}
    try:
        stock = _get_stock(ticker)
        hist = stock.history(period="3mo")
        if hist is None or hist.empty or len(hist) < 60:
            return result
        close = hist["Close"]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        if sma200 and sma50 > sma200:
            result["trend"] = "bullish"
        elif sma200 and sma50 < sma200:
            result["trend"] = "bearish"
        else:
            sma20 = close.rolling(20).mean().iloc[-1]
            pct = (close.iloc[-1] / sma20 - 1) * 100
            if abs(pct) < 3:
                result["trend"] = "sideways"
            elif pct > 0:
                result["trend"] = "bullish"
            else:
                result["trend"] = "bearish"
        atr20 = (hist["High"] - hist["Low"]).rolling(20).mean().iloc[-1]
        atr60 = (hist["High"] - hist["Low"]).rolling(60).mean().iloc[-1]
        if atr60 > 0 and (atr20 / atr60) > 1.3:
            result["volatility"] = "high"
        elif atr60 > 0 and (atr20 / atr60) < 0.7:
            result["volatility"] = "low"
        else:
            result["volatility"] = "normal"
        cache.set(f"mkt_regime_{ticker}", "strategy", result, ttl=600)
    except Exception as e:
        agent_state.log_source_result(f"regime:{ticker}", False, str(e))
    return result


def check_calendar_guard(ticker: str, holding_days: int = 30) -> Dict[str, Any]:
    cached = cache.get(f"cal_guard_{ticker}", "strategy")
    if cached:
        return _check_holding_window(cached, holding_days)
    try:
        stock = _get_stock(ticker)
        cal = stock.calendar
        if cal is None or cal.empty:
            return {"earnings": None, "ex_div": None, "has_conflict": False, "warning": ""}
        cal_dict = {}
        if hasattr(cal, "to_dict"):
            cal_dict = cal.to_dict()
        earnings_date = None
        ex_div_date = None
        if "Earnings Date" in cal.index:
            raw = cal.loc["Earnings Date"]
            if isinstance(raw, str):
                earnings_date = raw
            elif hasattr(raw, "isoformat"):
                earnings_date = raw.isoformat()[:10]
        if "Ex-Dividend Date" in cal.index:
            raw = cal.loc["Ex-Dividend Date"]
            if isinstance(raw, str):
                ex_div_date = raw
            elif hasattr(raw, "isoformat"):
                ex_div_date = raw.isoformat()[:10]
        result = {
            "earnings": earnings_date,
            "ex_div": ex_div_date,
            "opex": _next_opex(),
            "has_conflict": False,
            "warning": "",
        }
        cache.set(f"cal_guard_{ticker}", "strategy", {**result, "_raw": True})
        return _check_holding_window(result, holding_days)
    except Exception:
        return {"earnings": None, "ex_div": None, "has_conflict": False, "warning": ""}


def _check_holding_window(cal: Dict[str, Any], holding_days: int) -> Dict[str, Any]:
    cal = {**cal}
    cal["has_conflict"] = False
    warnings = []
    today = datetime.now()
    for event_key, label in [("earnings", "財報"), ("ex_div", "除息"), ("opex", "選擇權結算")]:
        val = cal.get(event_key)
        if val and isinstance(val, str):
            try:
                evt_date = datetime.strptime(val[:10], "%Y-%m-%d")
                days_until = (evt_date - today).days
                if 0 <= days_until <= holding_days:
                    warnings.append(f" 持有期內有{label} ({val[:10]})")
                    cal["has_conflict"] = True
            except ValueError:
                pass
    cal["warning"] = " | ".join(warnings)
    return cal


def _next_opex() -> Optional[str]:
    today = datetime.now()
    y, m = today.year, today.month
    if today.day > 15:
        m += 1
        if m > 12:
            m = 1
            y += 1
    third_friday = 21 - (datetime(y, m, 1).weekday() + 3) % 7
    return datetime(y, m, third_friday).strftime("%Y-%m-%d")


def _suggest_position_size(current_price: float, stop_price: float,
                           account_risk_pct: float = 0.02,
                           account_size: float = 10000) -> Dict[str, Any]:
    risk_per_share = abs(current_price - stop_price)
    if risk_per_share <= 0:
        return {"shares": 0, "max_loss_usd": 0, "position_value_usd": 0}
    max_loss_usd = account_size * account_risk_pct
    shares = int(max_loss_usd / risk_per_share)
    if shares < 1:
        shares = 0
    return {
        "shares": shares,
        "max_loss_usd": round(max_loss_usd, 0),
        "position_value_usd": round(shares * current_price, 2),
    }


def _get_relative_strength(ticker: str, sector: Optional[str] = None) -> Dict[str, Any]:
    cached = cache.get(f"rel_str_{ticker}", "strategy")
    if cached:
        return cached
    result = {"vs_spy_pct": None, "vs_sector_pct": None, "sector_etf": None}
    try:
        import pandas as pd
        end = datetime.now()
        start = end - timedelta(days=7)
        spy = yf.download("SPY", start=start.strftime("%Y-%m-%d"),
                          end=end.strftime("%Y-%m-%d"), progress=False)
        stock = _get_stock(ticker)
        sh = stock.history(start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"))
        if spy is not None and not spy.empty and sh is not None and not sh.empty:
            spy_close = spy["Close"].iloc[:, 0] if isinstance(spy["Close"], pd.DataFrame) else spy["Close"]
            sh_close = sh["Close"]
            spy_chg = float((spy_close.iloc[-1] / spy_close.iloc[0] - 1) * 100)
            st_chg = float((sh_close.iloc[-1] / sh_close.iloc[0] - 1) * 100)
            result["vs_spy_pct"] = round(st_chg - spy_chg, 2)
        sector_etf = SECTOR_ETF_MAP.get(sector) if sector else None
        if sector_etf:
            etf = yf.download(sector_etf, start=start.strftime("%Y-%m-%d"),
                              end=end.strftime("%Y-%m-%d"), progress=False)
            if etf is not None and not etf.empty:
                etf_close = etf["Close"].iloc[:, 0] if isinstance(etf["Close"], pd.DataFrame) else etf["Close"]
                etf_chg = float((etf_close.iloc[-1] / etf_close.iloc[0] - 1) * 100)
                result["vs_sector_pct"] = round(st_chg - etf_chg, 2) if not sh.empty else None
            result["sector_etf"] = sector_etf
        cache.set(f"rel_str_{ticker}", "strategy", result, ttl=600)
    except Exception:
        pass
    return result


# --- Strategy scorers ---

def score_trend_following(fundamental: Dict[str, Any],
                          technical: Dict[str, Any],
                          regime: Dict[str, str]) -> Dict[str, Any]:
    score = 0
    reasons = []
    if regime.get("trend") != "bullish":
        return {"score": 0, "entry_price": None, "stop_loss": None,
                "targets": [], "reasoning": "市況非多頭趨勢，不適合趨勢跟蹤策略"}
    score += 30
    reasons.append("大趨勢向上 (+30)")
    sma20 = technical.get("sma_20")
    sma50 = technical.get("sma_50")
    price = technical.get("price")
    if sma20 and sma50 and sma20 > sma50:
        score += 25
        reasons.append(f"SMA20({sma20:.1f}) > SMA50({sma50:.1f}) (+25)")
    rsi = technical.get("rsi_14")
    if rsi and 40 <= rsi <= 60:
        score += 20
        reasons.append(f"RSI 中性偏多 ({rsi:.0f}) (+20)")
    elif rsi and 30 <= rsi < 40:
        score += 15
        reasons.append(f"RSI 接近超賣，可逢低進場 (+15)")
    vol_ratio = technical.get("volume_ratio_10_50")
    if vol_ratio and vol_ratio > 0.8:
        score += 10
        reasons.append("量能正常 (+10)")
    macd = technical.get("macd_histogram")
    if macd and macd > 0:
        score += 15
        reasons.append("MACD 正柱 (+15)")
    score = min(score, 100)
    atr = technical.get("atr_14")
    entry = price
    stop = None
    targets = []
    if price and atr:
        stop = round(price - atr * ATR_STOP_MULTIPLIER, 2)
        targets = [
            {"price": round(price + atr * 3, 2), "size_pct": 33},
            {"price": round(price + atr * 5, 2), "size_pct": 33},
        ]
    elif price:
        stop = round(price * 0.93, 2)
        targets = [{"price": round(price * 1.07, 2), "size_pct": 33}]
    rr = round((targets[0]["price"] - entry) / (entry - stop), 1) if entry and stop and entry != stop else 0
    return {
        "score": score,
        "entry_price": entry,
        "stop_loss": stop,
        "targets": targets,
        "risk_reward": rr,
        "reasoning": " | ".join(reasons),
    }


def score_mean_reversion(fundamental: Dict[str, Any],
                         technical: Dict[str, Any],
                         regime: Dict[str, str],
                         calendar: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    reasons = []
    rsi = technical.get("rsi_14")
    bb_signal = technical.get("bb_signal")
    price = technical.get("price")
    if rsi and rsi <= RSI_OVERSOLD:
        score += 35
        reasons.append(f"RSI 超賣 ({rsi:.0f}) (+35)")
    elif rsi and rsi <= 40:
        score += 20
        reasons.append(f"RSI 接近超賣 ({rsi:.0f}) (+20)")
    if bb_signal == "below_lower":
        score += 25
        reasons.append("價格低於 BB 下軌 (+25)")
    elif bb_signal == "within" and price and technical.get("bb_lower"):
        dist = (price / technical["bb_lower"] - 1) * 100
        if dist < 5:
            score += 15
            reasons.append(f"價格接近 BB 下軌 ({dist:.1f}%) (+15)")
    macd = technical.get("macd_histogram")
    if macd and macd < 0:
        score += 15
        reasons.append("MACD 負柱，但可能為反轉做準備 (+15)")
    vol_ratio = technical.get("volume_ratio_10_50")
    if vol_ratio and vol_ratio < 0.5:
        score += 10
        reasons.append("量能萎縮，賣壓減輕 (+10)")
    elif vol_ratio and vol_ratio > 2:
        score -= 10
        reasons.append("爆量下跌，恐有續跌風險 (-10)")
    if calendar.get("has_conflict"):
        score = score // 2
        reasons.append("(已砍半)")
    score = max(0, min(score, 100))
    entry = price
    stop = None
    targets = []
    atr = technical.get("atr_14")
    if price and atr:
        stop = round(price - atr * ATR_STOP_MULTIPLIER, 2)
        targets = [
            {"price": round(price + atr * 2, 2), "size_pct": 50},
            {"price": round(price + atr * 4, 2), "size_pct": 50},
        ]
    elif price:
        stop = round(price * 0.92, 2)
        targets = [{"price": round(price * 1.05, 2), "size_pct": 50}]
    rr = round((targets[0]["price"] - entry) / (entry - stop), 1) if entry and stop and entry != stop else 0
    return {
        "score": score,
        "entry_price": entry,
        "stop_loss": stop,
        "targets": targets,
        "risk_reward": rr,
        "reasoning": " | ".join(reasons),
    }


def score_breakout_momentum(fundamental: Dict[str, Any],
                            technical: Dict[str, Any],
                            regime: Dict[str, str]) -> Dict[str, Any]:
    score = 0
    reasons = []
    price = technical.get("price")
    bb_signal = technical.get("bb_signal")
    bb_upper = technical.get("bb_upper")
    vol_ratio = technical.get("volume_ratio_10_50")
    if bb_signal == "above_upper":
        score += 30
        reasons.append("價格突破 BB 上軌 (+30)")
    elif bb_upper and price and price >= bb_upper * 0.98:
        score += 20
        reasons.append("價格接近 BB 上軌 (+20)")
    if vol_ratio and vol_ratio >= VOLUME_SPIKE_RATIO:
        score += 25
        reasons.append(f"量能放大 ({vol_ratio:.1f}×) (+25)")
    elif vol_ratio and vol_ratio < 1.2:
        reasons.append(f" 量能不足 ({vol_ratio:.1f}×)，假突破率高")
        score -= 10
    rsi = technical.get("rsi_14")
    if rsi and 50 <= rsi <= 70:
        score += 20
        reasons.append(f"RSI 動能區 ({rsi:.0f}) (+20)")
    elif rsi and rsi < 50:
        score += 5
        reasons.append("RSI 偏弱 (+5)")
    macd = technical.get("macd_histogram")
    if macd and macd > 0:
        score += 15
        reasons.append("MACD 正柱 (+15)")
    trend = technical.get("trend_signal")
    if trend == "uptrend":
        score += 10
        reasons.append("價格 > SMA50，大趨勢向上 (+10)")
    score = max(0, min(score, 100))
    entry = price
    stop = None
    targets = []
    atr = technical.get("atr_14")
    if price and atr:
        stop = round(price - atr * ATR_STOP_MULTIPLIER, 2)
        targets = [
            {"price": round(price + atr * 2.5, 2), "size_pct": 50},
            {"price": round(price + atr * 5, 2), "size_pct": 50},
        ]
    elif price:
        stop = round(price * 0.95, 2)
        targets = [{"price": round(price * 1.08, 2), "size_pct": 50}]
    rr = round((targets[0]["price"] - entry) / (entry - stop), 1) if entry and stop and entry != stop else 0
    return {
        "score": score,
        "entry_price": entry,
        "stop_loss": stop,
        "targets": targets,
        "risk_reward": rr,
        "reasoning": " | ".join(reasons),
    }


def score_value_entry(fundamental: Dict[str, Any],
                      technical: Dict[str, Any],
                      regime: Dict[str, str]) -> Dict[str, Any]:
    score = 0
    reasons = []
    peg = fundamental.get("peg")
    if peg is not None and peg > 0:
        if peg <= 0.5:
            score += 30
            reasons.append(f"PEG 極低 ({peg:.2f}) (+30)")
        elif peg <= 1.0:
            score += 25
            reasons.append(f"PEG 偏低 ({peg:.2f}) (+25)")
        elif peg <= 1.5:
            score += 15
            reasons.append(f"PEG 合理 ({peg:.2f}) (+15)")
    pe = fundamental.get("pe_ratio")
    if pe is not None and pe > 0:
        if pe <= 15:
            score += 15
            reasons.append(f"本益比低 ({pe:.1f}) (+15)")
        elif pe <= 25:
            score += 10
            reasons.append(f"本益比合理 ({pe:.1f}) (+10)")
    pb = fundamental.get("pb_ratio")
    if pb is not None and pb > 0 and pb <= 3:
        score += 10
        reasons.append(f"股價淨值比合理 ({pb:.2f}) (+10)")
    roe = fundamental.get("roe")
    if roe is not None:
        if roe >= 20:
            score += 15
            reasons.append(f"ROE 優秀 ({roe:.1f}%) (+15)")
        elif roe >= 10:
            score += 10
            reasons.append(f"ROE 良好 ({roe:.1f}%) (+10)")
    de = fundamental.get("debt_equity")
    if de is not None and de <= 1:
        score += 10
        reasons.append(f"負債比低 ({de:.2f}) (+10)")
    rev = fundamental.get("revenue_growth")
    if rev is not None and rev > 0:
        score += 10
        reasons.append(f"營收正成長 ({rev:.1f}%) (+10)")
    score = max(0, min(score, 100))
    return {
        "score": score,
        "entry_price": technical.get("price"),
        "stop_loss": None,
        "targets": [],
        "risk_reward": None,
        "reasoning": " | ".join(reasons),
    }


def score_income_defensive(fundamental: Dict[str, Any],
                           technical: Dict[str, Any],
                           regime: Dict[str, str]) -> Dict[str, Any]:
    score = 0
    reasons = []
    div = fundamental.get("dividend_yield")
    if div is not None and div > 0:
        dy_pct = div * 100
        if dy_pct >= 3:
            score += 30
            reasons.append(f"殖利率高 ({dy_pct:.2f}%) (+30)")
        elif dy_pct >= 2:
            score += 20
            reasons.append(f"殖利率良好 ({dy_pct:.2f}%) (+20)")
        elif dy_pct >= 1:
            score += 10
            reasons.append(f"有配息 ({dy_pct:.2f}%) (+10)")
    beta = fundamental.get("beta")
    if beta is not None:
        if beta < 0.8:
            score += 20
            reasons.append(f"低波動 (beta={beta:.2f}) (+20)")
        elif beta < 1.2:
            score += 10
            reasons.append(f"波動適中 (beta={beta:.2f}) (+10)")
    de = fundamental.get("debt_equity")
    if de is not None and de <= 1:
        score += 15
        reasons.append(f"財務穩健 (D/E={de:.2f}) (+15)")
    pe = fundamental.get("pe_ratio")
    if pe is not None and 0 < pe < 25:
        score += 10
        reasons.append(f"本益比合理 ({pe:.1f}) (+10)")
    mcap = fundamental.get("market_cap")
    if mcap and mcap >= 10e9:
        score += 15
        reasons.append("大型股，流動性佳 (+15)")
    rev = fundamental.get("revenue_growth")
    if rev is not None and rev > 0:
        score += 10
        reasons.append(f"營收成長 ({rev:.1f}%) (+10)")
    score = max(0, min(score, 100))
    return {
        "score": score,
        "entry_price": technical.get("price"),
        "stop_loss": None,
        "targets": [],
        "risk_reward": None,
        "reasoning": " | ".join(reasons),
    }


_SCORERS = {
    "trend_following": score_trend_following,
    "mean_reversion": score_mean_reversion,
    "breakout_momentum": score_breakout_momentum,
    "value_entry": score_value_entry,
    "income_defensive": score_income_defensive,
}


def _to_python(obj):
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, float | np.floating):
        return round(float(obj), 4)
    if isinstance(obj, int | np.integer):
        return int(obj)
    return obj


def recommend_strategies(
    ticker: str,
    fundamental_data: Dict[str, Any],
    technical_data: Dict[str, Any],
) -> Dict[str, Any]:
    cached = cache.get(f"strat_{ticker}", "strategy")
    if cached:
        return cached
    regime = detect_market_regime(ticker)
    calendar = check_calendar_guard(ticker)
    sector = fundamental_data.get("sector") if fundamental_data else None
    relative = _get_relative_strength(ticker, sector)
    opts = fetch_options_chain(ticker)
    results = []
    for sdef in STRATEGIES:
        sid = sdef["id"]
        scorer = _SCORERS.get(sid)
        if not scorer:
            continue
        sregime = sdef["suitable_regime"]
        if "any" not in sregime and regime.get("trend") not in sregime:
            results.append({
                "id": sid,
                "name_key": sdef["name_key"],
                "time_horizon": sdef["time_horizon"],
                "difficulty_key": sdef["difficulty_key"],
                "score": 0,
                "entry_price": None,
                "stop_loss": None,
                "targets": [],
                "risk_reward": None,
                "reasoning": f"不適合當前市況 ({regime.get('trend')})",
                "max_loss_usd": 0,
                "technical_confidence": 0,
                "fundamental_confidence": 0,
                "setup_quality": 0,
                "scenario": {},
            })
            continue
        try:
            kwargs = {"fundamental": fundamental_data, "technical": technical_data, "regime": regime}
            if sid == "mean_reversion":
                kwargs["calendar"] = calendar
            sr = scorer(**kwargs)
            pos = _suggest_position_size(
                sr.get("entry_price") or technical_data.get("price", 0),
                sr.get("stop_loss") or (technical_data.get("price", 0) * 0.95),
            )
            sr["max_loss_usd"] = pos.get("max_loss_usd", 0)
            sr["shares"] = pos.get("shares", 0)
            sr["position_value_usd"] = pos.get("position_value_usd", 0)
            sr["technical_confidence"] = min(100, int(sr["score"] * 0.7 + (
                (100 - technical_data.get("rsi_14", 50) if sid == "mean_reversion"
                 else technical_data.get("rsi_14", 50)) if technical_data.get("rsi_14") else 50
            ) * 0.3))
            sr["fundamental_confidence"] = min(100, int(fundamental_data.get("total_score", 50)))
            sr["setup_quality"] = min(100, int(
                sr["score"] * 0.6 + sr.get("risk_reward", 1) * 10
            ))
            sr["scenario"] = _generate_scenarios(
                sid, sr, technical_data, fundamental_data, regime
            )
            results.append({
                "id": sid,
                "name_key": sdef["name_key"],
                "time_horizon": sdef["time_horizon"],
                "difficulty_key": sdef["difficulty_key"],
                **sr,
            })
        except Exception as e:
            agent_state.log_source_result(f"strat_{sid}:{ticker}", False, str(e))
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = results[0] if results else {}
    out = {
        "rankings": results[:3],
        "top": top,
        "regime": regime,
        "calendar": calendar,
        "relative_strength": relative,
        "options_data": opts,
    }
    out = _to_python(out)
    cache.set(f"strat_{ticker}", "strategy", out, ttl=3600)
    return out


def _generate_scenarios(strategy_id: str, sr: Dict[str, Any],
                         technical: Dict[str, Any],
                         fundamental: Dict[str, Any],
                         regime: Dict[str, str]) -> Dict[str, str]:
    price = sr.get("entry_price") or technical.get("price", 0)
    stop = sr.get("stop_loss")
    targets = sr.get("targets", [])
    base = targets[0]["price"] if targets else round(price * 1.05, 2)
    best = targets[1]["price"] if len(targets) > 1 else round(price * 1.10, 2)
    worst = stop if stop else round(price * 0.92, 2)
    return {
        "best": f"目標達成 → ${best:.2f} (+{(best/price-1)*100:.1f}%)",
        "base": f"技術面持續好轉 → ${base:.2f} (+{(base/price-1)*100:.1f}%)",
        "worst": f"停損出場 → ${worst:.2f} ({(worst/price-1)*100:.1f}%)",
    }
