import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from utils.cache import Cache


def test_clear_removes_memory_and_disk_cache(tmp_path) -> None:
    cache = Cache()
    cache._dir = str(tmp_path)
    cache.set("ticker", "info", {"price": 100})

    cache.clear()

    assert cache.get("ticker", "info") is None


def test_clear_expired_preserves_unexpired_entries_across_categories(tmp_path) -> None:
    cache = Cache()
    cache._dir = str(tmp_path)
    cache.set("ticker", "info", {"price": 100}, ttl=3600)
    cache.set("financial", "financials", {"revenue": 10}, ttl=3600)

    cache.clear_expired()

    assert cache.get("ticker", "info") == {"price": 100}
    assert cache.get("financial", "financials") == {"revenue": 10}
