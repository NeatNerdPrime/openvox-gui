"""HTTP health probes for clustered compilers and PuppetDB nodes by FQDN."""
from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any, Dict, List

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=settings.puppet_ssl_ca)
    try:
        ctx.load_cert_chain(
            certfile=settings.puppet_ssl_cert,
            keyfile=settings.puppet_ssl_key,
        )
    except Exception as e:
        logger.debug("mTLS cert chain not loaded for cluster health: %s", e)
    return ctx


async def _probe_url(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    try:
        r = await client.get(url)
        body = (r.text or "").strip()[:200]
        healthy = r.status_code == 200 and (
            body in ("running", "ok", "true") or "running" in body.lower()
        )
        return {
            "url": url,
            "http_status": r.status_code,
            "body": body,
            "healthy": healthy,
            "error": None,
        }
    except Exception as e:
        return {
            "url": url,
            "http_status": None,
            "body": "",
            "healthy": False,
            "error": str(e),
        }


async def probe_cluster_members(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Probe each compiler (:8140) and PuppetDB node (:8081) by FQDN."""
    members: List[Dict[str, Any]] = []
    compilers = cfg.get("compilers") or []
    pdb_nodes = cfg.get("puppetdb_nodes") or []

    verify = _ssl_context()
    timeout = httpx.Timeout(5.0, connect=3.0)

    async with httpx.AsyncClient(verify=verify, timeout=timeout) as client:
        tasks = []
        meta: List[Dict[str, str]] = []
        for fqdn in compilers:
            url = f"https://{fqdn}:8140/status/v1/simple"
            tasks.append(_probe_url(client, url))
            meta.append({"fqdn": fqdn, "role": "compiler", "port": "8140"})
        for fqdn in pdb_nodes:
            url = f"https://{fqdn}:8081/status/v1/simple"
            tasks.append(_probe_url(client, url))
            meta.append({"fqdn": fqdn, "role": "puppetdb", "port": "8081"})

        if not tasks:
            return []

        results = await asyncio.gather(*tasks)
        for m, r in zip(meta, results):
            members.append({**m, **r})

    return members
