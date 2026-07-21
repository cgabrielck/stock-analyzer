import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backtesting.universe import HistoricalUniverse


def test_historical_universe_uses_latest_snapshot_without_lookahead(tmp_path) -> None:
    path = tmp_path / "universe.json"
    path.write_text(json.dumps({"snapshots": {
        "2020-01-01": ["A", "B"],
        "2021-01-01": ["B", "C"],
    }}))
    universe = HistoricalUniverse(path=path)

    assert universe.tickers_for(date(2020, 6, 1)) == ["A", "B"]
    assert universe.tickers_for(date(2021, 6, 1)) == ["B", "C"]
    assert universe.uses_current_universe_fallback is False


def test_selected_custom_ticker_is_available_without_snapshots(tmp_path) -> None:
    universe = HistoricalUniverse(path=tmp_path / "missing.json", selected_tickers=["CUSTOM"])

    assert universe.all_tickers() == ["CUSTOM"]
    assert universe.tickers_for(date(2024, 1, 1)) == ["CUSTOM"]
