import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import data_fetcher


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
