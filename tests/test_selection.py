import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from utils.selection import MIN_RECOMMENDATION_METRICS, select_recommendations


def test_selection_fills_below_entry_while_preserving_sector_cap() -> None:
    scored = [
        {"ticker": "A", "sector": "Tech", "total_score": 80},
        {"ticker": "B", "sector": "Tech", "total_score": 70},
        {"ticker": "C", "sector": "Tech", "total_score": 59},
        {"ticker": "D", "sector": "Health", "total_score": 58},
        {"ticker": "E", "sector": "Energy", "total_score": 57},
        {"ticker": "F", "sector": "Finance", "total_score": 56},
    ]

    selected = select_recommendations(scored)

    assert [stock["ticker"] for stock in selected] == ["A", "B", "D", "E", "F"]


def test_selection_can_require_minimum_metrics() -> None:
    scored = [
        {"ticker": "A", "sector": "Tech", "total_score": 90, "metrics_used": 3},
        {"ticker": "B", "sector": "Health", "total_score": 80, "metrics_used": 4},
    ]

    assert [stock["ticker"] for stock in select_recommendations(scored, min_metrics=4)] == ["B"]
    assert MIN_RECOMMENDATION_METRICS == 4


def test_selection_limits_satellite_positions_and_requires_higher_score() -> None:
    scored = [
        {"ticker": "S1", "sector": "Space", "total_score": 80, "universe_tier": "satellite"},
        {"ticker": "S2", "sector": "Consumer", "total_score": 75, "universe_tier": "satellite"},
        {"ticker": "S3", "sector": "Energy", "total_score": 64, "universe_tier": "satellite"},
        {"ticker": "A", "sector": "Tech", "total_score": 63, "universe_tier": "core"},
        {"ticker": "B", "sector": "Health", "total_score": 62, "universe_tier": "core"},
    ]

    selected = select_recommendations(scored, max_satellite=1, satellite_threshold=65)

    assert [stock["ticker"] for stock in selected] == ["S1", "A", "B"]
