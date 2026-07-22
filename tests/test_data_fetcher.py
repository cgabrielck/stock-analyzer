import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import data_fetcher
from datetime import date, timedelta


class _Response:
    def raise_for_status(self) -> None:
        pass

    def json(self):
        return {
            "quoteSummary": {
                "result": [{"financialData": {"debtToEquity": {"raw": 150.0}}}]
            }
        }


def test_yahoo_debt_equity_is_normalized_to_ratio(monkeypatch) -> None:
    monkeypatch.setattr(data_fetcher._REQUEST_SESSION, "get", lambda *args, **kwargs: _Response())

    result = data_fetcher._fetch_yahoo_fundamentals("TEST")

    assert result["debt_equity"] == 1.5


def test_extract_news_supports_new_yahoo_schema() -> None:
    result = data_fetcher._extract_news({"content": {
        "id": "article-1", "title": "Earnings beat", "summary": "Revenue increased",
        "pubDate": "2026-07-22T10:00:00Z", "provider": {"displayName": "Reuters"},
        "canonicalUrl": {"url": "https://example.com/new"}, "contentType": "STORY",
    }})

    assert result["id"] == "article-1"
    assert result["publisher"] == "Reuters"
    assert result["published_at"].startswith("2026-07-22T10:00:00")


def test_extract_news_supports_legacy_yahoo_schema() -> None:
    result = data_fetcher._extract_news({
        "uuid": "legacy", "title": "Legacy story", "publisher": "AP",
        "link": "https://example.com/legacy", "providerPublishTime": 1784714400,
    })

    assert result["id"] == "legacy"
    assert result["publisher"] == "AP"
    assert result["link"].endswith("legacy")
    assert result["published_at"] is not None


def test_calendar_dates_support_current_dict_shape() -> None:
    future = date.today() + timedelta(days=10)

    dates = data_fetcher._calendar_earnings_dates({"Earnings Date": [future]})

    assert dates == [future]


def test_news_relevance_rejects_unrelated_company_story() -> None:
    assert data_fetcher._news_is_relevant("AAPL", "Apple raises guidance", "") is True
    assert data_fetcher._news_is_relevant("AAPL", "Zhongji seeks Hong Kong listing", "China optical company") is False
