from typing import Any, Dict, List, Optional


MIN_RECOMMENDATION_METRICS: int = 4


def select_recommendations(
    scored: List[Dict[str, Any]],
    *,
    entry_threshold: float = 60.0,
    fill_threshold: float = 50.0,
    max_per_sector: int = 2,
    top_n: int = 5,
    min_metrics: Optional[int] = None,
    score_field: str = "total_score",
    max_satellite: int = 1,
    satellite_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Select ranked stocks with the same threshold and sector rules everywhere."""
    eligible = [
        stock for stock in scored
        if min_metrics is None or stock.get("metrics_used", 0) >= min_metrics
    ]
    ranked = sorted(
        eligible,
        key=lambda stock: stock.get(score_field, 0) or 0,
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    sector_count: Dict[str, int] = {}
    satellite_count = 0

    def add_from_pool(minimum_score: float) -> None:
        nonlocal satellite_count
        for stock in ranked:
            ticker = stock.get("ticker")
            score = stock.get(score_field, 0) or 0
            is_satellite = stock.get("universe_tier") == "satellite"
            required_score = max(minimum_score, satellite_threshold or minimum_score) if is_satellite else minimum_score
            if ticker in selected_ids or score < required_score:
                continue
            if is_satellite and satellite_count >= max_satellite:
                continue
            sector = stock.get("sector") or "Unknown"
            if sector_count.get(sector, 0) >= max_per_sector:
                continue
            selected.append(stock)
            selected_ids.add(ticker)
            sector_count[sector] = sector_count.get(sector, 0) + 1
            satellite_count += int(is_satellite)
            if len(selected) >= top_n:
                return

    add_from_pool(entry_threshold)
    if len(selected) < top_n:
        add_from_pool(fill_threshold)
    return selected
