"""Process-local TTL cache used by dashboard / metrics endpoints."""
from __future__ import annotations

import asyncio

from app.utils import ttl_cache


def setup_function():
    ttl_cache.invalidate()


def test_get_miss_then_hit():
    assert ttl_cache.get("k", ttl=10) is None
    ttl_cache.set("k", {"ok": True})
    assert ttl_cache.get("k", ttl=10) == {"ok": True}


def test_get_expires():
    ttl_cache.set("stale", 1)
    assert ttl_cache.get("stale", ttl=-1) is None


def test_invalidate_prefix():
    ttl_cache.set("dash:a", 1)
    ttl_cache.set("dash:b", 2)
    ttl_cache.set("other", 3)
    dropped = ttl_cache.invalidate("dash:")
    assert dropped == 2
    assert ttl_cache.get("other", ttl=10) == 3
    assert ttl_cache.get("dash:a", ttl=10) is None


def test_invalidate_all():
    ttl_cache.set("a", 1)
    ttl_cache.set("b", 2)
    assert ttl_cache.invalidate() == 2
    assert ttl_cache.get("a", ttl=10) is None


async def test_get_or_set_single_flight():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        await asyncio.sleep(0.01)
        return "value"

    first, second = await asyncio.gather(
        ttl_cache.get_or_set("sf", 10, factory),
        ttl_cache.get_or_set("sf", 10, factory),
    )
    assert first == second == "value"
    assert calls["n"] == 1
