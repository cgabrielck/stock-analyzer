import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import deep_research
from agents.deep_research import (
    _avoid_assessment,
    _build_options_plan,
    _build_trade_plan,
    _long_term_score,
    _short_term_score,
)


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
    monkeypatch.setattr(deep_research, "fetch_options_chain", lambda *args, **kwargs: {"error": "none"})
    monkeypatch.setattr(deep_research, "fetch_trading_session_ranges", lambda *args, **kwargs: {"sessions": {}})
    monkeypatch.setattr(deep_research, "suggest_trading_strategy", lambda *args, **kwargs: {"reasoning": "ok"})

    result = deep_research.analyze_ticker("AAPL")

    assert fetched == ["AAPL"]
    assert result["ticker"] == "AAPL"
    assert result["quant_score"] is not None


def test_bullish_trade_plan_has_ordered_levels() -> None:
    technical = {"price": 100, "atr_14": 4, "ema_21": 97, "sma_50": 94, "bb_lower": 92, "bb_upper": 106}

    plan = _build_trade_plan({}, technical, 75, 70, {"active": False})

    assert plan["stance"] == "bullish"
    assert plan["stop_loss"] < plan["entry_zone"]["low"] < plan["entry_zone"]["high"]
    assert plan["targets"][0] > plan["entry_zone"]["high"]


def test_bearish_trade_plan_has_ordered_levels() -> None:
    technical = {"price": 100, "atr_14": 4, "ema_21": 103, "sma_50": 106, "bb_lower": 94, "bb_upper": 108}

    plan = _build_trade_plan({}, technical, 35, 40, {"active": True})

    assert plan["stance"] == "bearish"
    assert plan["stop_loss"] > plan["entry_zone"]["high"]
    assert plan["targets"][0] < plan["entry_zone"]["low"]


def test_options_plan_selects_liquid_contract_and_sets_premium_exits() -> None:
    options = {
        "selected_expiry": "2026-08-21",
        "calls": [
            {"strike": 100, "bid": 2.0, "ask": 4.0, "mid": 3.0, "open_interest": 10, "volume": 0, "spread_pct": 66.7},
            {"strike": 105, "bid": 2.4, "ask": 2.6, "mid": 2.5, "open_interest": 500, "volume": 100, "spread_pct": 8.0},
        ],
        "puts": [],
    }

    plan = _build_options_plan(options, {"stance": "bullish", "stop_loss": 95})

    assert plan["action"] == "buy_to_open"
    assert plan["contract"]["strike"] == 105
    assert plan["max_entry_premium"] == 2.6
    assert plan["stop_premium"] < plan["max_entry_premium"] < plan["take_profit_premiums"][0]


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


def test_analyze_tickers_runs_in_parallel_and_preserves_order(monkeypatch) -> None:
    def analyze(ticker, **kwargs):
        time.sleep(0.1)
        return {"ticker": ticker}

    monkeypatch.setattr(deep_research, "analyze_ticker", analyze)
    started = time.monotonic()

    results = deep_research.analyze_tickers(["AAPL", "MSFT", "NVDA"])

    assert time.monotonic() - started < 0.25
    assert list(results) == ["AAPL", "MSFT", "NVDA"]


def test_analyze_ticker_emits_stage_progress(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(deep_research, "fetch_stock_data", lambda *args, **kwargs: {
        "ticker": "AAPL", "revenue_growth": 20, "eps_growth": 20, "profit_margin": 20,
        "peg": 1, "roe": 20, "debt_equity": 0.5,
    })
    monkeypatch.setattr(deep_research, "compute_technical_indicators", lambda *args, **kwargs: {
        "technical_score": 70, "price": 100, "risk_metrics": {"available": False},
        "ema_9": 101, "ema_21": 100, "ema_50": 95, "sma_50": 96, "adx_14": 25,
    })
    monkeypatch.setattr(deep_research, "fetch_news", lambda *args, **kwargs: [])
    monkeypatch.setattr(deep_research, "fetch_options_chain", lambda *args, **kwargs: {"error": "none"})
    monkeypatch.setattr(deep_research, "fetch_trading_session_ranges", lambda *args, **kwargs: {"sessions": {}})
    monkeypatch.setattr(deep_research, "suggest_trading_strategy", lambda *args, **kwargs: {"reasoning": "ok"})

    deep_research.analyze_ticker("AAPL", progress_callback=events.append)

    completed = {event["stage"] for event in events if event["state"] == "completed"}
    assert completed == {"fundamental", "technical", "market_data", "strategy"}


def test_batch_progress_completes_ticker_after_stage_events(monkeypatch) -> None:
    def analyze(ticker, progress_callback=None, **kwargs):
        progress_callback({"ticker": ticker, "stage": "strategy", "state": "completed"})
        return {"ticker": ticker}

    events = []
    monkeypatch.setattr(deep_research, "analyze_ticker", analyze)

    deep_research.analyze_tickers(["AAPL"], progress_callback=events.append)

    assert events[-1] == {"ticker": "AAPL", "stage": "ticker", "state": "completed"}
