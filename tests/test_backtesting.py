import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backtesting.engine import _extract_fundamentals_as_of


def test_historical_peg_uses_price_available_on_rebalance_date() -> None:
    columns = pd.to_datetime([
        "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31",
    ])
    financials = pd.DataFrame(
        [
            [120, 110, 105, 100, 100],
            [2.4, 2.2, 2.1, 2.0, 2.0],
            [24, 22, 21, 20, 20],
        ],
        index=["Total Revenue", "Diluted EPS", "Net Income"],
        columns=columns,
    )
    balance_sheet = pd.DataFrame(
        [[100, 95, 90, 85, 80], [20, 20, 20, 20, 20]],
        index=["Stockholders Equity", "Total Debt"],
        columns=columns,
    )
    prices = pd.DataFrame(
        {"Close": [100.0, 1_000.0]},
        index=pd.to_datetime(["2025-03-31", "2026-01-01"]),
    )

    data = _extract_fundamentals_as_of(
        financials,
        balance_sheet,
        prices,
        pd.Timestamp("2025-03-31"),
    )

    # 2024 Q4 EPS growth is 20%; PEG must use the $100 rebalance-date close,
    # not the $1,000 close that arrives later in the price dataframe.
    assert round(data["peg"], 2) == 208.33


def test_historical_fundamentals_are_not_substituted_with_future_reports() -> None:
    financials = pd.DataFrame(
        [[100], [2]],
        index=["Total Revenue", "Diluted EPS"],
        columns=pd.to_datetime(["2025-12-31"]),
    )

    assert _extract_fundamentals_as_of(
        financials,
        None,
        None,
        pd.Timestamp("2025-03-31"),
    ) == {}
