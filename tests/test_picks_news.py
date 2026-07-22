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


def test_impact_cache_key_changes_with_content_and_stable_earnings_context() -> None:
    article = {"id": "1", "title": "Title", "summary": "Summary", "published_at": "2026-07-22T00:00:00Z"}
    earnings = {"available": True, "date_start": "2026-07-30", "date_end": "2026-07-30", "days_until": 8, "source": "yahoo"}

    first = picks_news._impact_cache_key("AAPL", article, earnings, "en")
    updated = picks_news._impact_cache_key("AAPL", {**article, "summary": "Updated"}, earnings, "en")
    next_day = picks_news._impact_cache_key("AAPL", article, {**earnings, "days_until": 7}, "en")

    assert first != updated
    assert first == next_day
