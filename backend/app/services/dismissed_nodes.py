"""Operator-dismissed certnames hidden from live-fleet UI lists."""
from __future__ import annotations

import logging
from typing import Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.dismissed_node import DismissedNode
from ..utils.ttl_cache import invalidate as cache_invalidate

logger = logging.getLogger(__name__)


async def dismissed_certnames(db: AsyncSession | None = None) -> Set[str]:
    """Lowercased certnames the operator has dismissed as ghosts."""
    if db is not None:
        result = await db.execute(select(DismissedNode.certname))
        return {str(c).strip().lower() for c in result.scalars() if c}

    from ..database import async_session

    async with async_session() as session:
        result = await session.execute(select(DismissedNode.certname))
        return {str(c).strip().lower() for c in result.scalars() if c}


async def dismiss_node(
    db: AsyncSession,
    certname: str,
    *,
    dismissed_by: str = "",
    reason: str = "ghost",
) -> str:
    """Record *certname* as dismissed. Returns the stored certname."""
    cn = (certname or "").strip()
    if not cn:
        raise ValueError("certname is required")
    existing = await db.get(DismissedNode, cn)
    if existing is None:
        # Primary key is the exact string; also match case-insensitive
        result = await db.execute(
            select(DismissedNode).where(DismissedNode.certname == cn)
        )
        existing = result.scalar_one_or_none()
    if existing is None:
        db.add(
            DismissedNode(
                certname=cn,
                dismissed_by=(dismissed_by or "")[:128],
                reason=(reason or "ghost")[:255],
            )
        )
    else:
        existing.dismissed_by = (dismissed_by or existing.dismissed_by or "")[:128]
        existing.reason = (reason or existing.reason or "ghost")[:255]
    await db.commit()
    cache_invalidate("live_nodes")
    logger.info("Dismissed ghost node '%s' (by %s)", cn, dismissed_by or "?")
    return cn


async def undismiss_node(db: AsyncSession, certname: str) -> bool:
    cn = (certname or "").strip()
    if not cn:
        return False
    row = await db.get(DismissedNode, cn)
    if row is None:
        result = await db.execute(select(DismissedNode))
        for r in result.scalars():
            if str(r.certname).strip().lower() == cn.lower():
                row = r
                break
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    cache_invalidate("live_nodes")
    return True
