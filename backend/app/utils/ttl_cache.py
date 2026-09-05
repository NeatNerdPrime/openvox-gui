"""
Simple process-local TTL cache with optional single-flight locking.

Used by expensive read endpoints (dashboard, metrics, performance) so
repeated UI polls and multi-tab usage do not each hammer PuppetDB/JMX.

Notes:
- Per-process only. With uvicorn --workers N, each worker has its own map
  (still effective: each worker amortizes its own load).
- Values should be JSON-serializable plain data (dicts/lists), not ORM
  instances or open connections.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_store: Dict[str, Any] = {}
_ts: Dict[str, float] = {}
_locks: Dict[str, asyncio.Lock] = {}


def get(key: str, ttl: float) -> Optional[Any]:
    """Return cached value if present and younger than *ttl* seconds."""
    if key in _store and (time.time() - _ts.get(key, 0.0)) < ttl:
        return _store[key]
    return None


def set(key: str, value: Any) -> None:
    _store[key] = value
    _ts[key] = time.time()


def invalidate(prefix: str = "") -> int:
    """Drop keys starting with *prefix* (or all if prefix empty). Returns count."""
    keys = [k for k in list(_store.keys()) if not prefix or k.startswith(prefix)]
    for k in keys:
        _store.pop(k, None)
        _ts.pop(k, None)
        _locks.pop(k, None)
    return len(keys)


def _is_empty_result(value: Any) -> bool:
    """True for an empty fleet payload that must not replace a good cache."""
    if value is None:
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict):
        nodes = value.get("nodes")
        if isinstance(nodes, list) and len(nodes) == 0:
            status = value.get("node_status") or {}
            if not status.get("total"):
                return True
    return False


def fleet_size(value: Any) -> int:
    """How many nodes a live_nodes list or dashboard payload represents."""
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        nodes = value.get("nodes")
        if isinstance(nodes, list) and nodes:
            return len(nodes)
        status = value.get("node_status") or {}
        try:
            return int(status.get("total") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


# Keep last-good when a VIP backend / site PDB returns a tiny slice.
_SHRINK_HOLD_SECONDS = 7200.0


def is_worse_fleet(new: Any, stale: Any, stale_age: float = 0.0) -> bool:
    """True when *new* must not replace *stale* on screen.

    A 1-node (or <50%) probe against a known fleet is almost always
    the other console's empty-ish PuppetDB during a VIP flap — not a
    real decommission. After ``_SHRINK_HOLD_SECONDS`` we accept the
    smaller set so genuine shrinks eventually land.
    """
    if stale is None:
        return False
    if _is_empty_result(new):
        return True
    old_n = fleet_size(stale)
    new_n = fleet_size(new)
    if old_n <= 1 or new_n >= old_n:
        return False
    if stale_age > _SHRINK_HOLD_SECONDS and not _is_empty_result(new):
        return False
    if old_n >= 3 and new_n <= 1:
        return True
    if new_n < max(2, int(old_n * 0.5)):
        return True
    return False


def _annotate_last_good(value: Any, probe: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    out["fleet_view"] = {
        "source": "last_good",
        "probe_count": fleet_size(probe),
        "shown_count": fleet_size(value),
    }
    return out


async def get_or_set(
    key: str,
    ttl: float,
    factory: Callable[[], Awaitable[T]],
) -> T:
    """Return cached value or compute it once (single-flight under lock).

    A failed factory or an empty fleet payload keeps the last good
    value even after TTL (stale-if-error). Do not cache empty lists.
    """
    hit = get(key, ttl)
    if hit is not None:
        return hit  # type: ignore[return-value]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = get(key, ttl)
        if hit is not None:
            return hit  # type: ignore[return-value]
        stale = _store.get(key)
        stale_ts = _ts.get(key, 0.0)
        if stale is None:
            try:
                from ..services.fleet_last_good import load as load_last_good

                stale = await load_last_good(key)
                if stale is not None:
                    _store[key] = stale
                    _ts[key] = time.time()
                    stale_ts = _ts[key]
            except Exception:
                logger.debug("cache %s last-good load skipped", key, exc_info=True)
        try:
            value = await factory()
        except Exception:
            if stale is not None:
                logger.warning(
                    "cache %s factory failed; serving last-good (%d nodes)",
                    key,
                    fleet_size(stale),
                    exc_info=True,
                )
                return _annotate_last_good(stale, None)  # type: ignore[return-value]
            raise
        stale_age = (time.time() - stale_ts) if stale is not None and stale_ts else 0.0
        if stale is not None and is_worse_fleet(value, stale, stale_age):
            logger.warning(
                "cache %s probe has %d nodes (had %d); keeping last-good",
                key,
                fleet_size(value),
                fleet_size(stale),
            )
            return _annotate_last_good(stale, value)  # type: ignore[return-value]
        if not _is_empty_result(value):
            set(key, value)
            try:
                from ..services.fleet_last_good import save as save_last_good

                await save_last_good(key, value, fleet_size(value))
            except Exception:
                logger.debug("cache %s last-good save skipped", key, exc_info=True)
        return value
