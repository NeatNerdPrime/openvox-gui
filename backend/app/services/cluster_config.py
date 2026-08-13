"""
Cluster / multi-server configuration for openvox-gui.

Single-server (default) keeps the historic singleton UX. When
``deployment_mode`` is ``clustered``, the UI exposes multi-compiler
code deploy, infrastructure ENC groups, and per-FQDN service health.

Access rule of thumb (data plane for code/ENC discovery):
  - **single** (all-in-one): prefer **local files** — codedir, r10k.yaml,
    puppet.conf, local puppetserver/PuppetDB on this host.
  - **clustered** (dedicated console): prefer **HTTP APIs + Bolt** to
    compilers / deploy targets — no control_repo on the GUI host.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings

logger = logging.getLogger(__name__)

_FQDN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

DEFAULT_CONFIG: Dict[str, Any] = {
    "deployment_mode": "single",  # single | clustered
    "compilers": [],  # list of FQDNs (catalog compilers / deploy targets)
    "puppetdb_nodes": [],  # list of FQDNs (OpenVoxDB application hosts)
    "ca_nodes": [],  # list of CA member FQDNs (ovca1, ovca2 per site)
    "ca_vips": [],  # optional CA VIP FQDNs (ovca.pdxc…, ovca.corp…)
    "code_deploy_targets": [],  # FQDNs that receive r10k stage/activate (defaults to compilers)
    "consoles": [],  # GUI FQDNs (openvox.pdxc…, openvox.atlc…)
    "database_backend": "sqlite",  # sqlite | postgresql
    "enc_api_urls": [],  # ENC script failover list, e.g. https://openvox.pdxc…:4567
    "staging_codedir": "/etc/puppetlabs/code-staging",
    "live_codedir": "/etc/puppetlabs/code",
}


def _config_path() -> Path:
    return Path(settings.data_dir) / "cluster_config.json"


def _validate_fqdn(name: str) -> str:
    n = (name or "").strip().lower()
    if not n or len(n) > 253 or not _FQDN_RE.match(n):
        raise ValueError(f"Invalid FQDN: {name!r}")
    return n


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return out
    mode = data.get("deployment_mode", "single")
    if mode not in ("single", "clustered"):
        mode = "single"
    out["deployment_mode"] = mode

    backend = str(data.get("database_backend") or "sqlite").strip().lower()
    if backend not in ("sqlite", "postgresql"):
        backend = "sqlite"
    out["database_backend"] = backend

    raw_urls = data.get("enc_api_urls") or []
    if isinstance(raw_urls, str):
        raw_urls = [u.strip() for u in raw_urls.replace(",", "\n").splitlines() if u.strip()]
    urls: List[str] = []
    if isinstance(raw_urls, list):
        for u in raw_urls:
            s = str(u).strip().rstrip("/")
            if s.startswith("https://") or s.startswith("http://"):
                urls.append(s)
    out["enc_api_urls"] = list(dict.fromkeys(urls))

    for key in ("compilers", "puppetdb_nodes", "ca_nodes", "ca_vips", "code_deploy_targets", "consoles"):
        raw = data.get(key) or []
        if not isinstance(raw, list):
            raw = []
        cleaned: List[str] = []
        for item in raw:
            try:
                cleaned.append(_validate_fqdn(str(item)))
            except ValueError:
                logger.warning("Skipping invalid FQDN in %s: %r", key, item)
        # de-dupe preserve order
        seen = set()
        uniq = []
        for c in cleaned:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        out[key] = uniq

    for key in ("staging_codedir", "live_codedir"):
        val = data.get(key) or DEFAULT_CONFIG[key]
        if isinstance(val, str) and val.startswith("/") and ".." not in val:
            out[key] = val

    # Default deploy targets to compilers when clustered and empty
    if out["deployment_mode"] == "clustered" and not out["code_deploy_targets"]:
        out["code_deploy_targets"] = list(out["compilers"])

    return out


def load_cluster_config() -> Dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _normalize(data)
    except Exception as e:
        logger.error("Failed to load cluster_config.json: %s", e)
        return dict(DEFAULT_CONFIG)


def save_cluster_config(
    data: Dict[str, Any],
    *,
    require_postgres_url: bool = False,
) -> Dict[str, Any]:
    """Persist cluster_config.json.

    When deployment_mode is clustered, database_backend is forced to
    postgresql. If require_postgres_url is True (config API when enabling
    clustered), the running settings.database_url must already be Postgres
    or the caller must be writing a postgres URL in the same request.
    """
    normalized = _normalize(data)
    if normalized.get("deployment_mode") == "clustered":
        normalized["database_backend"] = "postgresql"
        if require_postgres_url:
            url = (settings.database_url or "").strip().lower()
            if not url.startswith(("postgresql", "postgres")):
                raise ValueError(
                    "Clustered mode requires a PostgreSQL application database "
                    "(OPENVOX_GUI_DATABASE_URL=postgresql+asyncpg://…/openvox_gui). "
                    "Provide database_url in this request, or run "
                    "scripts/bootstrap-openvox-gui-db.sh / install with "
                    "OPENVOX_GUI_DB_BACKEND=postgresql first. SQLite cannot "
                    "support a second console or durable multi-host DR."
                )
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    logger.info(
        "Saved cluster config mode=%s compilers=%s puppetdb=%s deploy=%s backend=%s",
        normalized["deployment_mode"],
        len(normalized["compilers"]),
        len(normalized["puppetdb_nodes"]),
        len(normalized["code_deploy_targets"]),
        normalized.get("database_backend"),
    )
    return normalized


def is_clustered() -> bool:
    return load_cluster_config().get("deployment_mode") == "clustered"


def deploy_targets() -> List[str]:
    cfg = load_cluster_config()
    if cfg.get("deployment_mode") != "clustered":
        return []
    targets = cfg.get("code_deploy_targets") or cfg.get("compilers") or []
    return list(targets)
