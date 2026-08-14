"""
Console access mode: direct node FQDN vs VIP / load balancer.

Used so the SPA can keep aggressive polling on individual consoles
(openvox.pdxc…, openvox.atlc…) while softening refresh behind the
shared VIP (where multi-backend RR + hard 401 reloads caused logout
storms).
"""
from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Set

from fastapi import Request

from ..config import settings

logger = logging.getLogger(__name__)

# Absolute floor: never force-logout before 4h after login (product rule).
SESSION_MIN_SECONDS_FLOOR = 4 * 3600


def token_expire_hours() -> int:
    """JWT lifetime in hours — never below 4."""
    try:
        h = int(getattr(settings, "auth_token_hours", 24) or 24)
    except (TypeError, ValueError):
        h = 24
    return max(4, h)


def session_min_seconds() -> int:
    """Minimum session lifetime after login (seconds), ≥ 4h."""
    try:
        s = int(getattr(settings, "auth_session_timeout", SESSION_MIN_SECONDS_FLOOR) or SESSION_MIN_SECONDS_FLOOR)
    except (TypeError, ValueError):
        s = SESSION_MIN_SECONDS_FLOOR
    return max(SESSION_MIN_SECONDS_FLOOR, s)


def vip_poll_floor_ms() -> int:
    try:
        ms = int(getattr(settings, "vip_poll_floor_ms", 45000) or 45000)
    except (TypeError, ValueError):
        ms = 45000
    return max(15000, ms)


def _host_from_request(request: Request) -> str:
    # Prefer proxy-aware host if present; fall back to Host header.
    xf = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    raw = xf or (request.headers.get("host") or "")
    host = raw.split(":")[0].strip().lower()
    return host


def configured_vip_hosts() -> Set[str]:
    """Union of env OPENVOX_GUI_VIP_HOSTS and cluster_config vip_hosts."""
    hosts: Set[str] = set()
    raw = (getattr(settings, "vip_hosts", None) or "").strip()
    if raw:
        for part in raw.replace(",", " ").split():
            h = part.strip().lower().split(":")[0]
            if h:
                hosts.add(h)
    try:
        from .cluster_config import load_cluster_config

        cfg = load_cluster_config()
        for h in cfg.get("vip_hosts") or []:
            hosts.add(str(h).strip().lower())
    except Exception as exc:
        logger.debug("vip_hosts from cluster_config unavailable: %s", exc)
    return hosts


def local_console_hosts() -> Set[str]:
    """This node's identity + configured peer consoles (direct access)."""
    hosts: Set[str] = {"localhost", "127.0.0.1", "::1"}
    try:
        hosts.add(socket.gethostname().lower())
        hosts.add(socket.getfqdn().lower())
    except OSError:
        pass
    try:
        from .cluster_config import load_cluster_config

        cfg = load_cluster_config()
        for h in cfg.get("consoles") or []:
            hosts.add(str(h).strip().lower())
    except Exception:
        pass
    return hosts


def resolve_access_mode(request: Request) -> str:
    """Return 'vip' or 'direct' for this request's Host."""
    host = _host_from_request(request)
    if not host:
        return "direct"
    vips = configured_vip_hosts()
    if host in vips:
        return "vip"
    # If VIP list is empty but Host is not this node and not a known console,
    # still treat unknown public names cautiously only when clustered with
    # multiple consoles (shared LB hostname pattern). Prefer explicit vip_hosts.
    consoles = local_console_hosts()
    if vips:
        return "direct" if host in consoles or host not in vips else "vip"
    return "direct"


def access_status_payload(request: Request) -> Dict[str, Any]:
    """Fields merged into GET /api/auth/status for the SPA."""
    mode = resolve_access_mode(request)
    hours = token_expire_hours()
    return {
        "access_mode": mode,
        "session_ttl_seconds": hours * 3600,
        "session_min_seconds": session_min_seconds(),
        "vip_poll_floor_ms": vip_poll_floor_ms() if mode == "vip" else 0,
        "request_host": _host_from_request(request),
        "vip_hosts_configured": sorted(configured_vip_hosts()),
    }
