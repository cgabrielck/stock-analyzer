import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.deep_research import _avoid_assessment, _long_term_score, _short_term_score


def test_deep_scores_reward_aligned_ema_trend() -> None:
    stock = {"growth_score": 80, "risk_penalty": 0, "risk_penalty_level": "low", "metrics_used": 6}
    technical = {
        "technical_score": 75, "price": 120, "ema_9": 115, "ema_21": 110, "ema_50": 100,
        "ema_200": 90, "sma_50": 105, "sma_200": 95, "adx_14": 30,
    }

    assert _short_term_score(stock, technical) >= 75
    assert _long_term_score(stock, technical) >= 80


def test_avoid_requires_explainable_reasons() -> None:
    stock = {"risk_penalty_level": "high", "metrics_used": 6}
    technical = {"price": 80, "sma_50": 90, "sma_200": 100}

    result = _avoid_assessment(stock, technical, 40, 45)

    assert result["active"] is True
    assert len(result["reasons"]) >= 2
