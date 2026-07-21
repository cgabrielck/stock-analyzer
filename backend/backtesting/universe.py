import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from utils.constants import STOCK_UNIVERSE


DEFAULT_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "historical_universe.json"


class HistoricalUniverse:
    """Resolve dated universes from optional local snapshots, with an explicit fallback."""

    def __init__(self, path: Optional[Path] = None, selected_tickers: Optional[List[str]] = None) -> None:
        self.path = path or DEFAULT_HISTORY_PATH
        self.selected_tickers = set(selected_tickers or [])
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

    def _load_snapshots(self) -> Dict[str, List[str]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {
                str(key): [str(ticker) for ticker in values]
                for key, values in raw.get("snapshots", {}).items()
                if isinstance(values, list)
            }
        except (OSError, ValueError, TypeError):
            return {}
