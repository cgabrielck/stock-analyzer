from typing import Any, Dict, List, Optional, Tuple

from utils.constants import SCORING_WEIGHTS


def calculate_growth_score(
    data: Dict[str, Any],
    custom_weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, Dict[str, Dict[str, str]], int]:
    score = 0.0
    max_possible = 0.0
    details: Dict[str, Dict[str, str]] = {}
    metrics_used = 0

    w = custom_weights if custom_weights is not None else SCORING_WEIGHTS

    if data.get("revenue_growth") is not None and data["revenue_growth"] != 0:
        raw = data["revenue_growth"]
        s = min(max((raw / 20.0) * 100, 0), 100)
        score += s * w.get("revenue_growth", 0)
        max_possible += w.get("revenue_growth", 0) * 100
        details["营收增长 (YoY)"] = {"value": f"{raw:.1f}%", "score": f"{s:.0f}/100"}
        metrics_used += 1

    if data.get("eps_growth") is not None and data["eps_growth"] != 0:
        raw = data["eps_growth"]
        s = min(max((raw / 20.0) * 100, 0), 100)
        score += s * w.get("eps_growth", 0)
        max_possible += w.get("eps_growth", 0) * 100
        details["EPS增长 (YoY)"] = {"value": f"{raw:.1f}%", "score": f"{s:.0f}/100"}
        metrics_used += 1

    if data.get("profit_margin") is not None:
        raw = data["profit_margin"]
        s = min(max((raw / 20.0) * 100, 0), 100)
        score += s * w.get("profit_margin", 0)
        max_possible += w.get("profit_margin", 0) * 100
        details["净利润率"] = {"value": f"{raw:.1f}%", "score": f"{s:.0f}/100"}
        metrics_used += 1

    if data.get("peg") is not None and data["peg"] > 0:
        p = data["peg"]
        if p <= 0.5:
            s = 100
        elif p <= 1.0:
            s = 90
        elif p <= 1.5:
            s = 75
        elif p <= 2.0:
            s = 60
        elif p <= 3.0:
            s = 40
        elif p <= 5.0:
            s = 20
        else:
            s = 10
        score += s * w.get("peg_ratio", 0)
        max_possible += w.get("peg_ratio", 0) * 100
        details["PEG比率"] = {"value": f"{p:.2f}", "score": f"{s:.0f}/100"}
        metrics_used += 1

    if data.get("roe") is not None:
        raw = data["roe"]
        s = min(max((raw / 30.0) * 100, 0), 100)
        score += s * w.get("roe", 0)
        max_possible += w.get("roe", 0) * 100
        details["ROE"] = {"value": f"{raw:.1f}%", "score": f"{s:.0f}/100"}
        metrics_used += 1

    if data.get("debt_equity") is not None:
        d = data["debt_equity"]
        if d <= 0.3:
            s = 100
        elif d <= 0.5:
            s = 85
        elif d <= 1.0:
            s = 65
        elif d <= 2.0:
            s = 40
        elif d <= 3.0:
            s = 20
        else:
            s = 10
        score += s * w.get("debt_equity", 0)
        max_possible += w.get("debt_equity", 0) * 100
        details["负债/权益比"] = {"value": f"{d:.2f}", "score": f"{s:.0f}/100"}
        metrics_used += 1

    normalized = (score / max_possible) * 100 if max_possible > 0 else 0
    return round(normalized, 1), details, metrics_used


def calculate_all_scores(
    all_data: Dict[str, Dict[str, Any]],
    custom_weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for ticker, data in all_data.items():
        if "error" in data:
            continue
        if data.get("sector") is None:
            continue
        score, details, metrics_used = calculate_growth_score(data, custom_weights)
        data["growth_score"] = score
        data["score_details"] = details
        data["total_score"] = score
        data["metrics_used"] = metrics_used
        scored.append(data)
    scored.sort(key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    return scored
