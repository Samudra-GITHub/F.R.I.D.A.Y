"""Unit tests for WorldDataCache: TTL, freshness, stale snapshots, and deduplication locks."""

import asyncio
import time
import pytest
from backend.friday.world.cache import WorldDataCache


@pytest.mark.asyncio
async def test_cache_put_get_freshness():
    cache = WorldDataCache()
    cache.set("test_key", {"data": 42}, ttl_seconds=1.0)

    # Immediate get is fresh
    res = cache.get("test_key")
    assert res is not None
    data, is_stale, retrieved_at = res
    assert data == {"data": 42}
    assert is_stale is False
    assert "Z" in retrieved_at

    # After expiry, get() without allow_stale returns None
    await asyncio.sleep(1.05)
    assert cache.get("test_key", allow_stale=False) is None

    # With allow_stale=True, returns stale data
    stale_res = cache.get("test_key", allow_stale=True)
    assert stale_res is not None
    data, is_stale, _ = stale_res
    assert data == {"data": 42}
    assert is_stale is True


@pytest.mark.asyncio
async def test_last_successful_snapshot_fallback():
    cache = WorldDataCache()
    cache.set("provider_key", ["item1", "item2"], ttl_seconds=0.1)

    # Verify snapshot exists
    snap = cache.get_last_successful("provider_key")
    assert snap is not None
    items, timestamp = snap
    assert items == ["item1", "item2"]

    # Even after clearing primary entry manually
    cache._entries.pop("provider_key")
    assert cache.get("provider_key", allow_stale=False) is None
    assert cache.get("provider_key", allow_stale=True) is not None


@pytest.mark.asyncio
async def test_cache_deduplication_lock():
    cache = WorldDataCache()
    lock1 = await cache.get_lock("resource_A")
    lock2 = await cache.get_lock("resource_A")
    lock3 = await cache.get_lock("resource_B")

    assert lock1 is lock2
    assert lock1 is not lock3
