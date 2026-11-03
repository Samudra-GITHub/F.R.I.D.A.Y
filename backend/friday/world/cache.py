"""In-memory bounded cache with TTL, stale snapshots, and request deduplication.

Ensures reliable operations by caching external provider responses, isolating failures,
and providing stale-on-error fallback without making repeated external calls.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Generic, Optional, Tuple, TypeVar

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """An individual cache entry with freshness tracking."""

    def __init__(self, data: T, ttl_seconds: float, retrieved_at_epoch: Optional[float] = None) -> None:
        self.data: T = data
        self.ttl_seconds: float = ttl_seconds
        self.retrieved_at_epoch: float = retrieved_at_epoch if retrieved_at_epoch is not None else time.time()
        self.retrieved_at_iso: str = (
            datetime.fromtimestamp(self.retrieved_at_epoch, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def is_fresh(self, now: Optional[float] = None) -> bool:
        """Return True if within the configured TTL."""
        current_time = now if now is not None else time.time()
        return (current_time - self.retrieved_at_epoch) <= self.ttl_seconds


class WorldDataCache:
    """Thread-safe / async in-memory cache with stale fallback and deduplication locks."""

    def __init__(self) -> None:
        self._entries: Dict[str, CacheEntry[Any]] = {}
        self._last_successful: Dict[str, CacheEntry[Any]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get_lock(self, key: str) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock for a specific cache key."""
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    def get(self, key: str, allow_stale: bool = False) -> Optional[Tuple[Any, bool, str]]:
        """Retrieve cached data for key.
        
        Returns:
            Tuple of (data, is_stale, retrieved_at_iso) or None if absent.
        """
        entry = self._entries.get(key)
        if entry is None:
            if allow_stale:
                last_ok = self._last_successful.get(key)
                if last_ok:
                    return last_ok.data, True, last_ok.retrieved_at_iso
            return None

        now = time.time()
        if entry.is_fresh(now):
            return entry.data, False, entry.retrieved_at_iso

        if allow_stale:
            return entry.data, True, entry.retrieved_at_iso

        return None

    def set(self, key: str, data: Any, ttl_seconds: float) -> str:
        """Store fresh data in cache and snapshot it as last-successful."""
        entry = CacheEntry(data, ttl_seconds)
        self._entries[key] = entry
        self._last_successful[key] = entry
        return entry.retrieved_at_iso

    def get_last_successful(self, key: str) -> Optional[Tuple[Any, str]]:
        """Retrieve the last known good snapshot for the key."""
        entry = self._last_successful.get(key)
        if entry:
            return entry.data, entry.retrieved_at_iso
        return None

    def clear(self) -> None:
        """Clear all cached entries."""
        self._entries.clear()
        self._last_successful.clear()
        self._locks.clear()
