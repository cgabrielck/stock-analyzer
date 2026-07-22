import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import picks_news


def test_ticker_news_keeps_articles_when_ai_fails(monkeypatch) -> None:
    monkeypatch.setattr(picks_news, "fetch_news", lambda *args, **kwargs: [{
        "ticker": "AAPL", "id": "1", "title": "Apple raises guidance",
        "summary": "Outlook increased", "sentiment": "positive",
    }])
    monkeypatch.setattr(picks_news, "fetch_next_earnings", lambda *args, **kwargs: {"available": False})
    monkeypatch.setattr(picks_news, "analyze_news_impact", lambda *args, **kwargs: {"error": "offline"})

    result = picks_news.analyze_ticker_news("AAPL", include_ai=True)

    assert result["status"] == "partial"
    assert len(result["items"]) == 1
    assert result["items"][0]["analysis_source"] == "rules"
    assert result["items"][0]["impact"]["event_type"] == "guidance"


def test_batch_news_isolates_ticker_failures(monkeypatch) -> None:
    def analyze(ticker, *args, **kwargs):
        if ticker == "BAD":
            raise RuntimeError("failed")
        return {"ticker": ticker, "status": "ok", "items": []}

    monkeypatch.setattr(picks_news, "analyze_ticker_news", analyze)
    result = picks_news.analyze_picks_news(["AAPL", "BAD", "MSFT"])

    assert result["AAPL"]["status"] == "ok"
    assert result["BAD"]["status"] == "error"
    assert result["MSFT"]["status"] == "ok"
