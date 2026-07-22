import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from utils.constants import STOCK_UNIVERSE


DEFAULT_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "historical_universe.json"


class HistoricalUniverse:
    """Resolve dated universes from optional local snapshots, with an explicit fallback."""

    def __init__(self, path: Optional[Path] = None, selected_tickers: Optional[List[str]] = None) -> None:
        self.path = path or DEFAULT_HISTORY_PATH
        self.selected_tickers = set(selected_tickers or [])
        self.validation_errors: List[str] = []
        self.source_status = "historical_snapshots"
        self.snapshots = self._load_snapshots()
        self.uses_current_universe_fallback = not bool(self.snapshots)

    def tickers_for(self, as_of: date) -> List[str]:
        if self.snapshots:
            available = [key for key in self.snapshots if key <= as_of.isoformat()]
            tickers = self.snapshots[max(available)] if available else []
        else:
            tickers = list(self.selected_tickers) if self.selected_tickers else [stock["ticker"] for stock in STOCK_UNIVERSE]
        if self.selected_tickers:
            tickers = [ticker for ticker in tickers if ticker in self.selected_tickers]
        return sorted(tickers)

    def all_tickers(self) -> List[str]:
        if self.snapshots:
            tickers = {ticker for values in self.snapshots.values() for ticker in values}
        else:
            tickers = self.selected_tickers or {stock["ticker"] for stock in STOCK_UNIVERSE}
        if self.selected_tickers:
            tickers &= self.selected_tickers
        return sorted(tickers)

    def status(self) -> Dict[str, Any]:
        dates = sorted(self.snapshots)
        return {
            "state": self.source_status,
            "available": bool(self.snapshots),
            "historical_available": bool(self.snapshots),
            "uses_current_universe_fallback": self.uses_current_universe_fallback,
            "snapshot_count": len(dates),
            "first_snapshot": dates[0] if dates else None,
            "last_snapshot": dates[-1] if dates else None,
            "validation_errors": list(self.validation_errors),
        }

    def coverage_for(self, dates: Iterable[Union[date, datetime, str]]) -> Dict[str, Any]:
        requested = [self._date_string(value) for value in dates]
        snapshot_dates = sorted(self.snapshots)
        if snapshot_dates:
            missing = [value for value in requested if value < snapshot_dates[0]]
            covered = len(requested) - len(missing)
        else:
            missing = list(requested)
            covered = 0
        total = len(requested)
        return {
            "status": self.source_status,
            "requested_periods": total,
            "covered_periods": covered,
            "coverage_pct": round(covered / total * 100, 1) if total else 0.0,
            "missing_dates": missing,
            "before_first_snapshot": len(missing) if snapshot_dates else 0,
            "uses_current_universe_fallback": self.uses_current_universe_fallback,
            "historical_available": bool(self.snapshots),
        }

    def _load_snapshots(self) -> Dict[str, List[str]]:
        if not self.path.exists():
            self.source_status = "fallback_missing"
            self.validation_errors.append("snapshot_file_missing")
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            values = raw.get("snapshots") if isinstance(raw, dict) else None
            if not isinstance(values, dict) or not values:
                raise ValueError("snapshots must be a non-empty object")
            snapshots: Dict[str, List[str]] = {}
            for key, tickers in values.items():
                key_string = str(key)
                if date.fromisoformat(key_string).isoformat() != key_string:
                    raise ValueError(f"invalid snapshot date: {key_string}")
                if not isinstance(tickers, list) or not tickers:
                    raise ValueError(f"snapshot {key_string} must contain tickers")
                if any(not isinstance(ticker, str) or not ticker.strip() for ticker in tickers):
                    raise ValueError(f"snapshot {key_string} contains an invalid ticker")
                snapshots[key_string] = sorted(set(ticker.strip() for ticker in tickers))
            return snapshots
        except (OSError, ValueError, TypeError):
            self.source_status = "fallback_malformed"
            self.validation_errors.append("snapshot_file_malformed")
            return {}

    @staticmethod
    def _date_string(value: Union[date, datetime, str]) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return date.fromisoformat(str(value)).isoformat()
