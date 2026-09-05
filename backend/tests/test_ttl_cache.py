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


async def test_get_or_set_keeps_stale_on_factory_error():
    ttl_cache.set("dash", {"nodes": [{"certname": "a"}], "node_status": {"total": 1}})

    async def boom():
        raise RuntimeError("pdb down")

    got = await ttl_cache.get_or_set("dash", ttl=-1, factory=boom)
    assert got["node_status"]["total"] == 1


async def test_get_or_set_does_not_replace_good_with_empty():
    ttl_cache.set("live", [{"certname": "a"}])

    async def empty():
        return []

    got = await ttl_cache.get_or_set("live", ttl=-1, factory=empty)
    assert got == [{"certname": "a"}]


def test_is_worse_fleet_rejects_one_node_against_a_real_fleet():
    stale = [{"certname": f"n{i}"} for i in range(12)]
    probe = [{"certname": "lonely"}]
    assert ttl_cache.is_worse_fleet(probe, stale) is True
    assert ttl_cache.is_worse_fleet(stale, stale) is False
    assert ttl_cache.is_worse_fleet(stale + [{"certname": "x"}], stale) is False


def test_is_worse_fleet_accepts_shrink_after_hold():
    stale = [{"certname": f"n{i}"} for i in range(10)]
    probe = [{"certname": "lonely"}]
    assert ttl_cache.is_worse_fleet(probe, stale, stale_age=10) is True
    assert ttl_cache.is_worse_fleet(probe, stale, stale_age=8000) is False


async def test_get_or_set_keeps_last_good_when_probe_is_one_node():
    fleet = [{"certname": f"n{i}"} for i in range(8)]
    ttl_cache.set("live", fleet)

    async def tiny():
        return [{"certname": "only-me"}]

    got = await ttl_cache.get_or_set("live", ttl=-1, factory=tiny)
    assert ttl_cache.fleet_size(got) == 8
