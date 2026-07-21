import json
import os
import threading
import time
from typing import Any, Dict, Optional

from utils.constants import DATA_DIR


class Cache:
    def __init__(self) -> None:
        self._dir: str = os.path.join(DATA_DIR, "cache")
        os.makedirs(self._dir, exist_ok=True)
        self._mem_cache: Dict[str, Dict[str, Any]] = {}
        self._lock: threading.Lock = threading.Lock()

    def _path(self, category: str) -> str:
        return os.path.join(self._dir, f"{category}.json")

    def get(self, key: str, category: str, ttl: Optional[int] = None) -> Optional[Any]:
        with self._lock:
            from utils.constants import CACHE_TTL
            now = time.time()
            mem_key = f"{category}:{key}"
            if mem_key in self._mem_cache:
                entry = self._mem_cache[mem_key]
                if now - entry["ts"] < entry.get("ttl", CACHE_TTL.get(category, 86400)):
                    return entry["value"]
                del self._mem_cache[mem_key]

            path = self._path(category)
            if not os.path.exists(path):
                return None
            try:
                with open(path, "r") as f:
                    store: Dict[str, Any] = json.load(f)
            except (json.JSONDecodeError, OSError):
                return None
            if key not in store:
                return None
            entry = store[key]
            effective_ttl = ttl or CACHE_TTL.get(category, 86400)
            if now - entry["ts"] < effective_ttl:
                self._mem_cache[mem_key] = {"value": entry["value"], "ts": entry["ts"], "ttl": effective_ttl}
                return entry["value"]
            return None

    def set(self, key: str, category: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            from utils.constants import CACHE_TTL
            now = time.time()
            effective_ttl = ttl or CACHE_TTL.get(category, 86400)
            mem_key = f"{category}:{key}"
            self._mem_cache[mem_key] = {"value": value, "ts": now, "ttl": effective_ttl}
            path = self._path(category)
            store: Dict[str, Any] = {}
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        store = json.load(f)
                except (json.JSONDecodeError, OSError):
                    store = {}
            store[key] = {"value": value, "ts": now}
            with open(path, "w") as f:
                json.dump(store, f, indent=2)

    def delete(self, key: str, category: str) -> None:
        with self._lock:
            mem_key = f"{category}:{key}"
            self._mem_cache.pop(mem_key, None)
            path = self._path(category)
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        store = json.load(f)
                except (json.JSONDecodeError, OSError):
                    return
                store.pop(key, None)
                with open(path, "w") as f:
                    json.dump(store, f, indent=2)

    def clear(self, category: Optional[str] = None) -> None:
        """Clear memory and disk entries, including those held by a Cloud worker."""
        with self._lock:
            if category is None:
                self._mem_cache.clear()
                categories = [fname[:-5] for fname in os.listdir(self._dir) if fname.endswith(".json")]
            else:
                self._mem_cache = {
                    key: value for key, value in self._mem_cache.items()
                    if not key.startswith(f"{category}:")
                }
                categories = [category]

            for name in categories:
                path = self._path(name)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def clear_expired(self) -> None:
        with self._lock:
            from utils.constants import CACHE_TTL
            now = time.time()
            for fname in os.listdir(self._dir):
                if not fname.endswith(".json"):
                    continue
                category = fname[:-5]
                path = os.path.join(self._dir, fname)
                try:
                    with open(path, "r") as f:
                        store = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                ttl = CACHE_TTL.get(category, 86400)
                store = {k: v for k, v in store.items() if now - v["ts"] < ttl}
                with open(path, "w") as f:
                    json.dump(store, f, indent=2)
                self._mem_cache = {k: v for k, v in self._mem_cache.items()
                                   if k.startswith(f"{category}:") and now - v["ts"] < ttl}

    def get_cache_status(self) -> Dict[str, Any]:
        with self._lock:
            status: Dict[str, Any] = {}
            for fname in os.listdir(self._dir):
                if not fname.endswith(".json"):
                    continue
                category = fname[:-5]
                path = os.path.join(self._dir, fname)
                try:
                    with open(path, "r") as f:
                        store = json.load(f)
                except (json.JSONDecodeError, OSError):
                    store = {}
                status[category] = {"keys": len(store), "file": fname}
            return status


cache = Cache()
