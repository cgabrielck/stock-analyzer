import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import deep_research
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


def test_analyze_ticker_fetches_only_requested_stock(monkeypatch) -> None:
    fetched = []
    monkeypatch.setattr(deep_research, "fetch_stock_data", lambda ticker, force_refresh=False: fetched.append(ticker) or {
        "ticker": ticker, "revenue_growth": 20, "eps_growth": 20, "profit_margin": 20,
        "peg": 1, "roe": 20, "debt_equity": 0.5,
    })
    monkeypatch.setattr(deep_research, "compute_technical_indicators", lambda *args, **kwargs: {
        "technical_score": 70, "price": 100, "risk_metrics": {"available": False},
        "ema_9": 101, "ema_21": 100, "ema_50": 95, "ema_200": 80, "sma_50": 96,
        "sma_200": 82, "adx_14": 25,
    })
    monkeypatch.setattr(deep_research, "fetch_news", lambda *args, **kwargs: [])
    monkeypatch.setattr(deep_research, "suggest_trading_strategy", lambda *args, **kwargs: {"reasoning": "ok"})

    result = deep_research.analyze_ticker("AAPL")

    assert fetched == ["AAPL"]
    assert result["ticker"] == "AAPL"
    assert result["quant_score"] is not None


def test_analyze_tickers_keeps_partial_failures(monkeypatch) -> None:
    def analyze(ticker, **kwargs):
        if ticker == "BAD":
            raise RuntimeError("failed")
        return {"ticker": ticker}

    monkeypatch.setattr(deep_research, "analyze_ticker", analyze)

    results = deep_research.analyze_tickers(["AAPL", "BAD", "MSFT"])

    assert results["AAPL"] == {"ticker": "AAPL"}
    assert results["BAD"]["stage"] == "unexpected"
    assert results["MSFT"] == {"ticker": "MSFT"}
