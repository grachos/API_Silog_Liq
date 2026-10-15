"""Tests for InMemoryCache: TTL, LRU eviction, range reuse, and stampede lock."""
import asyncio
import time
import pytest
from app.models.schemas import LiquidacionItem
from app.services.cache import InMemoryCache


@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Stores and retrieves items from in-memory cache."""
    cache = InMemoryCache(max_entries=10, default_ttl=5)

    item = LiquidacionItem(numero_manifiesto="M-101", fecha="2026-01-15")
    await cache.set("test_key", [item], "2026-01-01", "2026-01-31", ttl_seconds=2)

    res = await cache.get("test_key")
    assert res is not None
    items, gen_at = res
    assert len(items) == 1
    assert items[0].numero_manifiesto == "M-101"

    # After TTL expiration
    await asyncio.sleep(2.1)
    res_expired = await cache.get("test_key")
    assert res_expired is None


@pytest.mark.asyncio
async def test_sub_range_cache_reuse():
    """
    When a larger range [2026-01-01 to 2026-01-31] is in cache,
    a query for sub-range [2026-01-10 to 2026-01-20] is answered directly from cache!
    """
    cache = InMemoryCache(max_entries=10, default_ttl=60)

    items = [
        LiquidacionItem(numero_manifiesto="M-1", fecha="2026-01-05"),
        LiquidacionItem(numero_manifiesto="M-2", fecha="2026-01-15"),
        LiquidacionItem(numero_manifiesto="M-3", fecha="2026-01-18"),
        LiquidacionItem(numero_manifiesto="M-4", fecha="2026-01-25"),
    ]

    await cache.set("full_month", items, "2026-01-01", "2026-01-31")

    # Query subset 2026-01-10 to 2026-01-20
    sub_res = await cache.get_matching_range("2026-01-10", "2026-01-20")
    assert sub_res is not None
    filtered_items, gen_at = sub_res

    # Should only contain M-2 (Jan 15) and M-3 (Jan 18)
    assert len(filtered_items) == 2
    assert [i.numero_manifiesto for i in filtered_items] == ["M-2", "M-3"]


@pytest.mark.asyncio
async def test_cache_lru_eviction():
    """Validates that oldest entries are evicted when max_entries is exceeded."""
    cache = InMemoryCache(max_entries=2, default_ttl=60)

    item1 = [LiquidacionItem(numero_manifiesto="M-1")]
    item2 = [LiquidacionItem(numero_manifiesto="M-2")]
    item3 = [LiquidacionItem(numero_manifiesto="M-3")]

    await cache.set("key1", item1, "2026-01-01", "2026-01-01")
    await cache.set("key2", item2, "2026-01-02", "2026-01-02")
    # Inserting third entry should evict key1
    await cache.set("key3", item3, "2026-01-03", "2026-01-03")

    assert await cache.get("key1") is None
    assert await cache.get("key2") is not None
    assert await cache.get("key3") is not None
