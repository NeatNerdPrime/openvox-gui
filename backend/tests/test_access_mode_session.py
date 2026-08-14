"""VIP access mode + session floor (3.12.0-gamma.1)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import access_mode as am


def test_token_expire_hours_floor():
    with patch.object(am.settings, "auth_token_hours", 1):
        assert am.token_expire_hours() == 4
    with patch.object(am.settings, "auth_token_hours", 24):
        assert am.token_expire_hours() == 24


def test_session_min_seconds_floor():
    with patch.object(am.settings, "auth_session_timeout", 60):
        assert am.session_min_seconds() >= 4 * 3600


def test_resolve_access_mode_vip_from_env():
    req = MagicMock()
    req.headers = {"host": "openvox.corp.example.com:4567"}
    with patch.object(am.settings, "vip_hosts", "openvox.corp.example.com"):
        with patch.object(am, "configured_vip_hosts", return_value={"openvox.corp.example.com"}):
            assert am.resolve_access_mode(req) == "vip"


def test_resolve_access_mode_direct_console():
    req = MagicMock()
    req.headers = {"host": "openvox.pdxc.example.com:4567"}
    with patch.object(am, "configured_vip_hosts", return_value={"openvox.corp.example.com"}):
        assert am.resolve_access_mode(req) == "direct"


def test_denylist_fail_open_on_db_error():
    """Lookup exceptions must not treat valid JWTs as revoked (VIP thrash)."""
    import asyncio
    from app.middleware import auth_local as al

    async def _run():
        with patch.object(al, "async_session") as mock_session_factory:
            # Simulate DB failure inside the context manager
            mock_session_factory.side_effect = RuntimeError("db down")
            revoked = await al._is_jti_revoked("any-jti")
            assert revoked is False

    asyncio.get_event_loop().run_until_complete(_run())
