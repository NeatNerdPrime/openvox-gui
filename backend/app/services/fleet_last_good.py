"""Persist last-good fleet payloads in the app DB (shared across VIP consoles)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

LIVE_KEY = "live_nodes:v1"
DASH_KEY = "dashboard:data:v3"


async def load(key: str) -> Optional[Any]:
    try:
        from ..database import async_session
        from ..models.gui_kv import GuiKv
        from sqlalchemy import select

        async with async_session() as db:
            row = (await db.execute(select(GuiKv).where(GuiKv.key == key))).scalar_one_or_none()
            if row is None or not row.value_json:
                return None
            return json.loads(row.value_json)
    except Exception:
        logger.debug("fleet_last_good load %s failed", key, exc_info=True)
        return None


async def save(key: str, value: Any, node_count: int) -> None:
    try:
        from ..database import async_session
        from ..models.gui_kv import GuiKv
        from sqlalchemy import select

        payload = json.dumps(value, default=str)
        async with async_session() as db:
            row = (await db.execute(select(GuiKv).where(GuiKv.key == key))).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row is None:
                db.add(GuiKv(key=key, value_json=payload, node_count=node_count, updated_at=now))
            else:
                row.value_json = payload
                row.node_count = node_count
                row.updated_at = now
            await db.commit()
    except Exception:
        logger.debug("fleet_last_good save %s failed", key, exc_info=True)
