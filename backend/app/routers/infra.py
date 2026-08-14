from __future__ import annotations

"""
Infrastructure Tuning and Health API for ovox infra.

Provides endpoints that power `ovox infra health` and `ovox infra tune`.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


from ..dependencies import require_role, READ_ROLES
from ..services.puppetdb import puppetdb_service
from ..services.infra_config import InfraConfigService
from ..utils.sudo import run_sudo

router = APIRouter(prefix="/api/infra", tags=["infrastructure"])

_infra_config = InfraConfigService()

_AUTH = require_role(*READ_ROLES)


@router.get("/health")
async def infra_health(_user: str = Depends(_AUTH)):
    """Aggregated estate health for ``ovox infra health``.

    Discovers the full serving estate (each compiler **and** compiler VIP,
    each OpenVoxDB **and** PDB VIP, each CA member **and** CA VIP, consoles)
    from cluster_config + OPENVOX_GUI_* settings, then HTTP-probes each host.
    Local GUI systemd rows are included for the console you are talking to.

    Never 500s on partial probe failure — returns degraded rows instead.
    """
    from ..services.cluster_config import is_clustered
    from ..services.estate_inventory import cluster_cfg_for_probes, discover_serving_estate
    from ..services.puppetserver import puppetserver_service

    warnings: List[str] = []
    mode = "clustered" if is_clustered() else "single"
    inventory = discover_serving_estate()
    ch: Dict[str, Any] = {}

    # Always probe full inventory (members + VIPs), not only .env VIP
    try:
        from ..services.cluster_health import probe_cluster_full

        ch = await probe_cluster_full(cluster_cfg_for_probes())
    except Exception as e:
        logger.exception("estate health probe failed")
        warnings.append(f"estate probe: {e}")
        ch = {}

    rows: List[Dict[str, Any]] = []
    seen: set = set()  # (role, host)

    def _add_row(
        component: str,
        role: str,
        host: str,
        status: str,
        source: str,
        detail: str,
        healthy: bool,
        kind: str = "member",
    ) -> None:
        key = (role, (host or "").lower())
        if key in seen and host:
            return
        if host:
            seen.add(key)
        rows.append({
            "component": component,
            "role": role,
            "kind": kind,
            "host": host,
            "status": status,
            "source": source,
            "detail": (detail or "")[:200],
            "healthy": healthy,
        })

    # Flatten probe results: members first, then VIPs (stable order)
    probe_groups = (
        ("compilers", "compiler", "member"),
        ("compiler_vips", "compiler-vip", "vip"),
        ("puppetdb_nodes", "puppetdb", "member"),
        ("puppetdb_vips", "puppetdb-vip", "vip"),
        ("ca_nodes", "ca", "member"),
        ("ca_vips", "ca-vip", "vip"),
        ("consoles", "console", "member"),
        ("console_vips", "console-vip", "vip"),
    )
    for key, role, kind in probe_groups:
        for m in ch.get(key) or []:
            if not isinstance(m, dict):
                continue
            fqdn = m.get("fqdn") or m.get("host") or "?"
            healthy = bool(m.get("healthy"))
            simple = m.get("simple") if isinstance(m.get("simple"), dict) else {}
            body = ""
            if simple:
                body = str(
                    simple.get("body")
                    or simple.get("http_status")
                    or ""
                )
            err = m.get("error") or ""
            label = "VIP" if kind == "vip" else "node"
            _add_row(
                component=f"{role}:{fqdn}",
                role=role,
                host=fqdn,
                status="active" if healthy else "failed",
                source="http",
                detail=(body or err or label)[:200],
                healthy=healthy,
                kind=kind,
            )

    # Local console agent + GUI process (the machine running this API)
    for svc_name in ("puppet", "openvox-gui"):
        try:
            svc = puppetserver_service.get_service_status(svc_name)
            st = (svc.get("status") or "unknown").lower()
            _add_row(
                component=svc_name,
                role="local",
                host=svc.get("host") or "local",
                status=svc.get("status") or "unknown",
                source="local-systemd",
                detail=svc.get("error") or svc.get("since") or "",
                healthy=st in ("active", "running"),
                kind="local",
            )
        except Exception as e:
            _add_row(
                component=svc_name,
                role="local",
                host="local",
                status="unknown",
                source="local-systemd",
                detail=str(e),
                healthy=False,
                kind="local",
            )

    ha = ch.get("ha") or {}
    pcs = ha.get("pcs") if isinstance(ha, dict) else {}
    if isinstance(pcs, dict) and (pcs.get("primary_node") or pcs.get("vip_node")):
        _add_row(
            component="ca-ha",
            role="ha",
            host=pcs.get("vip_node") or pcs.get("primary_node") or "",
            status="active" if ha.get("available") else "degraded",
            source="pcs",
            detail=f"primary={pcs.get('primary_node')} vip_node={pcs.get('vip_node')}",
            healthy=bool(ha.get("available")),
            kind="ha",
        )

    # Warn if inventory looks VIP-only (ops forgot member FQDNs in cluster config)
    inv = ch.get("inventory") or inventory
    if inv:
        if inv.get("compiler_vips") and not inv.get("compilers"):
            warnings.append(
                "No compiler *members* in cluster config — only VIPs. "
                "Add ovcompiler1/2 FQDNs under Settings → Cluster → compilers."
            )
        if inv.get("puppetdb_vips") and not inv.get("puppetdb_nodes"):
            warnings.append(
                "No OpenVoxDB *members* in cluster config — only VIP. "
                "Add ovdb1/2… under Settings → Cluster → puppetdb_nodes."
            )

    unhealthy = [r for r in rows if not r.get("healthy")]
    overall = (
        "ok" if not unhealthy
        else ("degraded" if any(r.get("healthy") for r in rows) else "critical")
    )

    return {
        "status": overall,
        "deployment_mode": mode,
        "inventory": inv,
        "components": rows,
        "services": [
            {
                "service": r["component"],
                "status": r["status"],
                "host": r.get("host"),
                "source": r.get("source"),
                "kind": r.get("kind"),
                "role": r.get("role"),
                "error": None if r.get("healthy") else (r.get("detail") or "unhealthy"),
                "memory": "",
                "since": "",
            }
            for r in rows
        ],
        "summary": ch.get("summary") if isinstance(ch, dict) else {},
        "warnings": warnings,
    }


@router.get("/settings")
async def get_infra_settings(
    component: Optional[str] = None,
    _user: str = Depends(_AUTH),
):
    """
    Return current key tuning settings for OpenVox Server and/or PuppetDB.

    This powers `ovox infra settings show`. On a dedicated console (clustered),
    local puppetserver/puppetdb conf often do not exist — return nulls with
    a note rather than 500.
    """
    from ..services.cluster_config import is_clustered

    result: Dict[str, Any] = {
        "deployment_mode": "clustered" if is_clustered() else "single",
    }

    try:
        if not component or component in ("server", "puppetserver"):
            try:
                jruby = _infra_config.get_puppetserver_jruby_max_active()
                jvm = _infra_config.get_puppetserver_jvm_settings()
            except Exception as e:
                jruby, jvm = None, {"error": str(e)}
            result["puppetserver"] = {
                "jruby_max_active_instances": jruby,
                "jvm": jvm,
                "local_config_present": jruby is not None or bool(jvm),
            }

        if not component or component in ("db", "puppetdb"):
            try:
                pools = _infra_config.get_puppetdb_pool_settings()
                jvm = _infra_config.get_puppetdb_jvm_settings()
            except Exception as e:
                pools, jvm = {}, {"error": str(e)}
            result["puppetdb"] = {
                "pools": pools,
                "jvm": jvm,
                "local_config_present": bool(pools),
            }

        # Dedicated console: pull live values from remote members via Bolt
        if is_clustered():
            result["note"] = (
                "Clustered console: settings sampled from remote hosts via Bolt "
                "(cluster_config FQDNs). Static /etc bolt inventory.yaml is not used."
            )
            try:
                from ..services.infra_remote import sample_remote_infra_settings

                remote = await sample_remote_infra_settings()
                result["remote"] = remote
                ps = (remote.get("puppetserver") or {}).get("sample")
                if ps and not result.get("puppetserver", {}).get("local_config_present"):
                    result["puppetserver"] = {
                        "jruby_max_active_instances": ps.get("jruby_max_active_instances"),
                        "jvm": ps.get("jvm") or {},
                        "local_config_present": False,
                        "source_host": ps.get("host"),
                        "source": "bolt",
                    }
                pdb = (remote.get("puppetdb") or {}).get("sample")
                if pdb and not result.get("puppetdb", {}).get("local_config_present"):
                    result["puppetdb"] = {
                        "pools": pdb.get("pools") or {},
                        "jvm": pdb.get("jvm") or {},
                        "local_config_present": False,
                        "source_host": pdb.get("host"),
                        "source": "bolt",
                    }
                if remote.get("errors"):
                    result["warnings"] = remote["errors"]
            except Exception as e:
                logger.warning("remote infra settings via bolt failed: %s", e)
                result.setdefault("warnings", []).append(str(e))
    except Exception as e:
        logger.exception("Failed to collect infra settings")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read infrastructure settings: {str(e)}",
        )

    return result


@router.post("/settings/set")
async def set_infra_setting(
    request: SettingsSetRequest,
    _user: str = Depends(require_role("admin")),
):
    """
    Directly set a specific infrastructure setting.

    Supports keys like:
      - jruby.max_active_instances
      - jvm.heap
      - read_pool.max_connections
      - write_pool.max_connections

    Clustered dedicated consoles: refuses local apply (would only touch the
    GUI host). Apply on each compiler/ovdb until remote tune exists.
    """
    from ..services.cluster_config import is_clustered

    if is_clustered():
        raise HTTPException(
            status_code=400,
            detail=(
                "Clustered console: refusing local infra settings apply. "
                "This would only change the GUI host. Set JRuby/heap/pools on "
                "each compiler and OpenVoxDB node (SSH or future remote tune)."
            ),
        )

    comp = request.component.lower()
    setting = request.setting.lower()
    value = request.value

    try:
        if comp in ("server", "puppetserver"):
            if "jruby" in setting or "max_active" in setting:
                val = int(value)
                backup = _infra_config.set_puppetserver_jruby_max_active(val)
                await run_sudo(["systemctl", "restart", "puppetserver"], timeout=120)
                return {"status": "success", "backup_dir": str(backup), "restarted": True}

            elif "jvm" in setting and "heap" in setting:
                # Accept "8g", "8192m", or just "8"
                heap_gb = _parse_heap_to_gb(value)
                backup = _infra_config.set_puppetserver_jvm_heap(heap_gb)
                await run_sudo(["systemctl", "restart", "puppetserver"], timeout=120)
                return {"status": "success", "backup_dir": str(backup), "restarted": True}

            elif "reserved_code_cache" in setting or "code_cache" in setting:
                # Accept "1g", "512m", etc.
                size = _normalize_code_cache_size(value)
                backup = _infra_config.set_puppetserver_reserved_code_cache(size)
                await run_sudo(["systemctl", "restart", "puppetserver"], timeout=120)
                return {"status": "success", "backup_dir": str(backup), "restarted": True}

        elif comp in ("db", "puppetdb"):
            if "read" in setting:
                val = int(value)
                backup = _infra_config.set_puppetdb_pool_settings(read_max=val)
                await run_sudo(["systemctl", "restart", "puppetdb"], timeout=120)
                return {"status": "success", "backup_dir": str(backup), "restarted": True}

            if "write" in setting:
                val = int(value)
                backup = _infra_config.set_puppetdb_pool_settings(write_max=val)
                await run_sudo(["systemctl", "restart", "puppetdb"], timeout=120)
                return {"status": "success", "backup_dir": str(backup), "restarted": True}

        raise HTTPException(status_code=400, detail=f"Unsupported setting '{setting}' for component '{comp}'")

    except Exception as e:
        logger.exception("settings/set failed")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_heap_to_gb(value: str) -> int:
    """Convert '8g', '8192m', '8' into integer GB."""
    value = value.lower().strip()
    if value.endswith("g"):
        return int(value[:-1])
    if value.endswith("m"):
        return max(1, int(value[:-1]) // 1024)
    return int(value)


def _normalize_code_cache_size(value: str) -> str:
    """Normalize '1g', '512m', '1024m' etc. into a consistent form."""
    v = value.lower().strip()
    if v.endswith("g") or v.endswith("m"):
        return v
    # Assume megabytes if no unit
    return f"{v}m"


@router.get("/tune/recommendations")
async def get_tune_recommendations(
    component: Optional[str] = None,
    _user: str = Depends(_AUTH),
) -> Dict[str, Any]:
    """
    Return current tuning parameters and recommendations for the
    OpenVox infrastructure (Puppet Server and PuppetDB).

    This is the data source for `ovox infra tune --recommend`.
    """
    from ..services.cluster_config import is_clustered, load_cluster_config

    try:
        nodes = await puppetdb_service.get_live_nodes()
        node_count = len(nodes)
    except Exception:
        try:
            nodes = await puppetdb_service.get_nodes()
            node_count = len(nodes)
        except Exception:
            node_count = 0

    clustered = is_clustered()
    cfg = load_cluster_config() if clustered else {}
    n_compilers = len(cfg.get("compilers") or []) or 1

    recs = []

    # Fleet-size heuristics work from any console. "current" is local-only
    # unless we later Bolt-read each compiler/ovdb.
    if not component or component in ("puppetserver", "server"):
        try:
            current_jruby = _infra_config.get_puppetserver_jruby_max_active()
        except Exception:
            current_jruby = None
        # Per-compiler guideline when clustered
        per = max(1, min(12, (node_count // max(1, n_compilers) // 35) + 2))
        suggested_jrubies = per

        recs.append({
            "component": "puppetserver",
            "setting": "jruby-puppet.max-active-instances",
            "current": (
                str(current_jruby) if current_jruby is not None
                else ("n/a on dedicated console" if clustered else "not found")
            ),
            "recommended": suggested_jrubies,
            "reason": (
                f"~{node_count} live nodes"
                + (f", {n_compilers} compilers" if clustered else "")
                + ". Guideline: ~1 JRuby per 35-40 agents per compiler (capped)."
            ),
        })

        heap_gb = max(2, min(16, (node_count // max(1, n_compilers) // 80) + 3))
        recs.append({
            "component": "puppetserver",
            "setting": "JVM heap (-Xms/-Xmx)",
            "current": (
                "n/a on dedicated console — set on each compiler"
                if clustered else "see /etc/sysconfig/puppetserver"
            ),
            "recommended": f"-Xms{heap_gb}g -Xmx{heap_gb}g",
            "reason": "Match heap to workload per compiler. Monitor GC logs.",
        })

    if not component or component in ("puppetdb", "db"):
        try:
            pools = _infra_config.get_puppetdb_pool_settings()
        except Exception:
            pools = {}
        suggested_pool = max(15, min(150, (node_count // 8) + 15))

        recs.append({
            "component": "puppetdb",
            "setting": "read_pool.max_connections + write_pool.max_connections",
            "current": (
                f"read={pools.get('read')}, write={pools.get('write')}"
                if pools else (
                    "n/a on dedicated console — set on each ovdb"
                    if clustered else "not found"
                )
            ),
            "recommended": suggested_pool,
            "reason": "Scale DB connection pools with number of agents.",
        })

    note = "These are starting recommendations. Review before applying."
    if clustered:
        note += (
            " Clustered mode: apply changes on compiler/ovdb hosts "
            "(ovox infra tune --apply is local to the GUI host only today)."
        )

    return {
        "node_count": node_count,
        "deployment_mode": "clustered" if clustered else "single",
        "compilers": cfg.get("compilers") or [],
        "puppetdb_nodes": cfg.get("puppetdb_nodes") or [],
        "recommendations": recs,
        "note": note,
    }


class TuneApplyRequest(BaseModel):
    component: str  # "server" or "db" or "puppetserver" or "puppetdb"
    changes: list[dict]   # list of {setting, value}


class SettingsSetRequest(BaseModel):
    component: str   # "server" or "db"
    setting: str     # e.g. "jruby.max_active_instances", "jvm.heap", "read_pool.max_connections"
    value: str


@router.post("/tune/apply")
async def apply_tuning(
    request: TuneApplyRequest,
    _user: str = Depends(require_role("admin")),
):
    """
    Apply tuning changes for a subsystem.

    Responsibilities:
    - Create timestamped backups of relevant config files
    - Apply the requested setting changes
    - Restart the affected service (puppetserver or puppetdb)
    """
    import shutil
    from datetime import datetime
    from pathlib import Path
    import subprocess
    import asyncio

    from ..services.cluster_config import is_clustered

    if is_clustered():
        raise HTTPException(
            status_code=400,
            detail=(
                "Clustered console: refusing local infra tune apply. "
                "Apply on each compiler/OpenVoxDB host until remote tune ships."
            ),
        )

    comp = request.component.lower()
    if comp in ("server", "puppetserver"):
        service_name = "puppetserver"
        is_puppetserver = True
    elif comp in ("db", "puppetdb"):
        service_name = "puppetdb"
        is_puppetserver = False
    else:
        raise HTTPException(status_code=400, detail="Unknown component. Use 'server' or 'db'.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(f"/etc/puppetlabs/{service_name}/backups/ovox-infra-{timestamp}")
    applied_changes = []

    try:
        if is_puppetserver:
            # Apply JRuby tuning using the dedicated service (handles backup)
            for change in request.changes:
                setting = change.get("setting", "").lower()
                value = change.get("value")

                if "max-active" in setting or "jruby" in setting:
                    try:
                        val = int(value)
                        backup_dir = _infra_config.set_puppetserver_jruby_max_active(val)
                        applied_changes.append(f"puppetserver: jruby-puppet.max-active-instances = {val}")
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid JRuby value: {value}")

        else:
            # Apply PuppetDB pool tuning
            read_val = None
            write_val = None
            for change in request.changes:
                setting = change.get("setting", "").lower()
                try:
                    val = int(change.get("value"))
                except (ValueError, TypeError):
                    continue

                if "read" in setting:
                    read_val = val
                elif "write" in setting:
                    write_val = val

            if read_val is not None or write_val is not None:
                backup_dir = _infra_config.set_puppetdb_pool_settings(read_val, write_val)
                applied_changes.append(f"puppetdb: pools updated (read={read_val}, write={write_val})")

        # Restart the service
        restart_result = await run_sudo(["systemctl", "restart", service_name], timeout=120)
        restarted = restart_result.get("returncode") == 0

        return {
            "status": "success" if restarted else "partial",
            "component": service_name,
            "applied": applied_changes or ["No matching settings found to change"],
            "backup_dir": str(backup_dir) if 'backup_dir' in locals() else "N/A",
            "restarted": restarted,
            "restart_output": (restart_result.get("stdout", "") + restart_result.get("stderr", "")).strip(),
            "message": f"Tuning applied for {service_name}. Service restart {'succeeded' if restarted else 'failed - check logs'}."
        }

    except Exception as e:
        logger.exception("Infra tuning apply failed")
        raise HTTPException(status_code=500, detail=f"Failed to apply tuning for {service_name}: {str(e)}")


def _update_jruby_max_active_instances(conf_file: Path, new_value: str):
    """Update jruby-puppet.max-active-instances in puppetserver.conf (HOCON-ish)."""
    import re
    content = conf_file.read_text()

    # Common pattern in puppetserver.conf
    pattern = r'(jruby-puppet\s*:\s*\{[^}]*?max-active-instances\s*:\s*)(\d+)'
    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, rf'\g<1>{new_value}', content, flags=re.DOTALL)
    else:
        # Fallback: append under jruby-puppet if section exists
        if "jruby-puppet:" in content:
            new_content = re.sub(
                r'(jruby-puppet\s*:\s*\{)',
                rf'\1\n    max-active-instances: {new_value}',
                content
            )
        else:
            # Last resort: add the section
            new_content = content + f"\n\njruby-puppet: {{\n    max-active-instances: {new_value}\n}}\n"

    conf_file.write_text(new_content)


def _update_puppetdb_pool(conf_file: Path, setting: str, value: str):
    """Simple update for PuppetDB database.ini pool settings."""
    import configparser

    config = configparser.ConfigParser()
    config.read(str(conf_file))

    # PuppetDB uses sections like [read_pool] and [write_pool]
    if "read" in setting.lower():
        section = "read_pool"
    elif "write" in setting.lower():
        section = "write_pool"
    else:
        section = "database"

    if not config.has_section(section):
        config.add_section(section)

    key = "max_connections" if "max" in setting.lower() else setting.split(".")[-1]
    config.set(section, key, value)

    with open(conf_file, "w") as f:
        config.write(f)
