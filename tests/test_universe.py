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
    assert universe.status()["state"] == "fallback_missing"
    assert universe.coverage_for([date(2024, 1, 1)])["coverage_pct"] == 0.0


def test_historical_universe_reports_before_first_snapshot_gap(tmp_path) -> None:
    path = tmp_path / "universe.json"
    path.write_text(json.dumps({"snapshots": {"2021-01-01": ["A"]}}))
    universe = HistoricalUniverse(path=path)

    assert universe.tickers_for(date(2020, 12, 31)) == []
    assert universe.status()["available"] is True
    coverage = universe.coverage_for([date(2020, 12, 31), date(2021, 2, 1)])
    assert coverage["covered_periods"] == 1
    assert coverage["before_first_snapshot"] == 1
    assert coverage["coverage_pct"] == 50.0


def test_malformed_historical_universe_is_explicit_fallback(tmp_path) -> None:
    path = tmp_path / "universe.json"
    path.write_text(json.dumps({"snapshots": {"not-a-date": ["A"]}}))
    universe = HistoricalUniverse(path=path, selected_tickers=["CUSTOM"])

    assert universe.tickers_for(date(2024, 1, 1)) == ["CUSTOM"]
    assert universe.uses_current_universe_fallback is True
    assert universe.status()["state"] == "fallback_malformed"
    assert universe.status()["available"] is False
