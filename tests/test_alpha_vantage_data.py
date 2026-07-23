import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import alpha_vantage_data as alpha


def test_normalize_fundamentals_maps_percentages_and_statements() -> None:
    result = alpha.normalize_fundamentals("TEST", {
        "OVERVIEW": {
            "Name": "Test Corp", "MarketCapitalization": "1000000", "PEGRatio": "1.2",
            "ProfitMargin": "0.15", "ReturnOnEquityTTM": "0.20",
            "QuarterlyRevenueGrowthYOY": "0.10", "QuarterlyEarningsGrowthYOY": "0.25",
        },
        "BALANCE_SHEET": {"annualReports": [{
            "fiscalDateEnding": "2025-12-31", "totalDebt": "50", "totalShareholderEquity": "100",
        }]},
        "CASH_FLOW": {"annualReports": [{
            "fiscalDateEnding": "2025-12-31", "operatingCashflow": "120", "capitalExpenditures": "-20",
        }]},
    })

    assert result["profit_margin"] == 15.0
    assert result["roe"] == 20.0
    assert result["revenue_growth"] == 10.0
    assert result["eps_growth"] == 25.0
    assert result["debt_equity"] == 0.5
    assert result["fcf"] == 100.0
    assert result["_alpha_meta"]["as_of"] == "2025-12-31"


def test_normalize_daily_adjusted_anchors_prices_to_latest_raw_close() -> None:
    frame = alpha.normalize_daily_adjusted({
        "2026-01-01": {
            "1. open": "80", "2. high": "100", "3. low": "70", "4. close": "90",
            "5. adjusted close": "450", "6. volume": "500",
        },
        "2026-01-02": {
            "1. open": "100", "2. high": "110", "3. low": "90", "4. close": "100",
            "5. adjusted close": "1000", "6. volume": "1000",
        }
    })

    assert frame.loc[pd.Timestamp("2026-01-02"), "Open"] == 100
    assert frame.loc[pd.Timestamp("2026-01-02"), "Close"] == 100
    assert frame.loc[pd.Timestamp("2026-01-01"), "Open"] == 40
    assert frame.loc[pd.Timestamp("2026-01-01"), "Close"] == 45
    assert frame.loc[pd.Timestamp("2026-01-01"), "Volume"] == 1000
    assert frame.attrs["latest_adjustment_factor"] == 10


def test_request_hides_key_and_detects_rate_limit(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Note": "request limit reached"}

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "secret-value")
    monkeypatch.setattr(alpha.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(alpha, "_throttled_until", 0.0)

    try:
        alpha._request("OVERVIEW", "RATE_LIMIT_TEST", 60, True)
    except alpha.AlphaVantageRateLimitError as exc:
        assert "secret-value" not in str(exc)
    else:
        raise AssertionError("rate limit response must raise")


def test_missing_key_disables_provider(monkeypatch) -> None:
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.setattr(alpha, "get_api_key", lambda: None)

    assert alpha.fetch_fundamentals("TEST") is None
    assert alpha.fetch_daily_adjusted("TEST") is None


def test_balance_sheet_total_debt_fallback_is_not_double_counted() -> None:
    result = alpha.normalize_fundamentals("TEST", {
        "BALANCE_SHEET": {"annualReports": [{
            "fiscalDateEnding": "2025-12-31",
            "shortLongTermDebtTotal": "80",
            "longTermDebt": "50",
            "totalShareholderEquity": "100",
        }]},
    })

    assert result["debt_equity"] == 0.5
