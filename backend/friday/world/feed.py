"""Shared fetch-with-cache helper for world providers.

Same guarantees as the original providers: one in-flight request per key, fresh cache
first, the last good snapshot (marked stale) when the upstream fails, and an honest
error status when there is nothing to fall back to. Never fabricates data.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

import httpx

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)
T = TypeVar("T")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class UpstreamError(Exception):
    def __init__(self, status: ProviderStatus, details: str) -> None:
        super().__init__(details)
        self.status = status
        self.details = details


@dataclass
class FeedResult(Generic[T]):
    data: Optional[T]
    status: ProviderStatus
    retrieved_at: str
    is_stale: bool
    details: Optional[str] = None


async def cached_fetch(
    cache: WorldDataCache,
    key: str,
    ttl_seconds: float,
    fetch: Callable[[], Awaitable[T]],
    name: str,
    force_refresh: bool = False,
) -> FeedResult[T]:
    if not force_refresh:
        hit = cache.get(key)
        if hit:
            data, stale, at = hit
            return FeedResult(data, ProviderStatus.STALE if stale else ProviderStatus.OK, at, stale)

    lock = await cache.get_lock(key)
    async with lock:
        if not force_refresh:
            hit = cache.get(key)
            if hit:
                data, stale, at = hit
                return FeedResult(data, ProviderStatus.STALE if stale else ProviderStatus.OK, at, stale)
        try:
            data = await fetch()
            at = cache.set(key, data, ttl_seconds)
            return FeedResult(data, ProviderStatus.OK, at, False)
        except UpstreamError as exc:
            status, details = exc.status, exc.details
        except httpx.TimeoutException:
            status, details = ProviderStatus.TIMEOUT, f"Request to {name} timed out"
        except Exception as exc:  # network errors, malformed payloads
            logger.warning("%s fetch failed: %s", name, exc)
            status, details = ProviderStatus.PROVIDER_ERROR, f"{name}: {exc}"

    snapshot = cache.get_last_successful(key)
    if snapshot:
        data, at = snapshot
        return FeedResult(data, ProviderStatus.STALE, at, True, f"Serving last good snapshot: {details}")
    return FeedResult(None, status, utc_now_iso(), False, details)


def raise_for_upstream(resp: httpx.Response, name: str) -> None:
    if resp.status_code == 429:
        raise UpstreamError(ProviderStatus.RATE_LIMITED, f"{name} rate limit reached")
    if resp.status_code >= 400:
        raise UpstreamError(ProviderStatus.PROVIDER_ERROR, f"{name} returned HTTP {resp.status_code}")
