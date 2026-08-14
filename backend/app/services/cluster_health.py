"""
Cluster health probes for multi-server OpenVox estates.

When deployment_mode is clustered, operators need more than a VIP ping:

* Compilers / CA: Puppet Server status APIs on each FQDN :8140
* OpenVoxDB: PuppetDB status + meta APIs on each FQDN :8081
* CA HA: pcs / corosync / DRBD summary and which node is Promoted (primary)

Probes use mTLS certs from settings (same as other GUI → Puppet paths).
PCS is run locally when ``pcs`` is available (GUI on a CA node), otherwise
via ``bolt command run`` against the first configured CA FQDN.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import ssl
from pathlib import Path
from typing import Any, Dict, List, Optional

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


async def _get_json(
    client: httpx.AsyncClient, url: str
) -> Dict[str, Any]:
    try:
        r = await client.get(url)
        text = (r.text or "").strip()
        data: Any
        try:
            data = r.json() if text.startswith("{") or text.startswith("[") else text
        except Exception:
            data = text[:500]
        return {
            "url": url,
            "http_status": r.status_code,
            "ok": r.status_code == 200,
            "body": data if not isinstance(data, str) else data[:500],
            "error": None if r.status_code == 200 else f"HTTP {r.status_code}",
        }
    except Exception as e:
        return {
            "url": url,
            "http_status": None,
            "ok": False,
            "body": None,
            "error": str(e),
        }


async def _get_text(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    try:
        r = await client.get(url)
        body = (r.text or "").strip()[:300]
        healthy = r.status_code == 200 and (
            body in ("running", "ok", "true") or "running" in body.lower()
        )
        return {
            "url": url,
            "http_status": r.status_code,
            "body": body,
            "healthy": healthy,
            "error": None if healthy else (body or f"HTTP {r.status_code}"),
        }
    except Exception as e:
        return {
            "url": url,
            "http_status": None,
            "body": "",
            "healthy": False,
            "error": str(e),
        }


async def probe_compiler(client: httpx.AsyncClient, fqdn: str) -> Dict[str, Any]:
    """Puppet Server health on a compiler FQDN."""
    base = f"https://{fqdn}:8140"
    simple = await _get_text(client, f"{base}/status/v1/simple")
    # Some OpenVox/Puppet Server builds only answer /simple/master (or return
    # a non-"running" body on /simple). Try the master endpoint before failing.
    if not simple.get("healthy"):
        simple_m = await _get_text(client, f"{base}/status/v1/simple/master")
        if simple_m.get("healthy"):
            simple = simple_m
    services = await _get_json(client, f"{base}/status/v1/services")
    # master service state if present
    master_state = None
    if isinstance(services.get("body"), dict):
        body = services["body"]
        for key in ("master", "pe-master", "puppetlabs.services.master.master-service/master-service"):
            if key in body and isinstance(body[key], dict):
                master_state = body[key].get("state") or body[key].get("status")
                break
        # generic: any service state
        if master_state is None:
            for _k, v in body.items():
                if isinstance(v, dict) and "state" in v:
                    master_state = v.get("state")
                    break

    healthy = bool(simple.get("healthy"))
    return {
        "fqdn": fqdn,
        "role": "compiler",
        "port": 8140,
        "healthy": healthy,
        "simple": simple,
        "services": {
            "ok": services.get("ok"),
            "http_status": services.get("http_status"),
            "error": services.get("error"),
            "master_state": master_state,
            # keep payload small for UI
            "service_keys": list(services["body"].keys())[:20]
            if isinstance(services.get("body"), dict)
            else [],
        },
        "error": simple.get("error") if not healthy else None,
    }


async def probe_ca(client: httpx.AsyncClient, fqdn: str) -> Dict[str, Any]:
    """CA / Puppet Server health on a CA FQDN (or VIP)."""
    base = f"https://{fqdn}:8140"
    simple = await _get_text(client, f"{base}/status/v1/simple")
    services = await _get_json(client, f"{base}/status/v1/services")
    ca_state = None
    if isinstance(services.get("body"), dict):
        body = services["body"]
        for key, v in body.items():
            if not isinstance(v, dict):
                continue
            kl = str(key).lower()
            if "ca" in kl or "certificate" in kl:
                ca_state = v.get("state") or v.get("status")
                break

    # CA certificate endpoint (public)
    ca_cert = await _get_text(client, f"{base}/puppet-ca/v1/certificate/ca")
    ca_cert_ok = bool(ca_cert.get("http_status") == 200) or (
        ca_cert.get("body") or ""
    ).startswith("-----BEGIN")

    healthy = bool(simple.get("healthy"))
    return {
        "fqdn": fqdn,
        "role": "ca",
        "port": 8140,
        "healthy": healthy,
        "simple": simple,
        "services": {
            "ok": services.get("ok"),
            "http_status": services.get("http_status"),
            "error": services.get("error"),
            "ca_state": ca_state,
            "service_keys": list(services["body"].keys())[:20]
            if isinstance(services.get("body"), dict)
            else [],
        },
        "ca_certificate_endpoint": {
            "ok": ca_cert_ok,
            "http_status": ca_cert.get("http_status"),
            "error": ca_cert.get("error"),
        },
        "error": simple.get("error") if not healthy else None,
    }


async def probe_puppetdb(client: httpx.AsyncClient, fqdn: str) -> Dict[str, Any]:
    """OpenVoxDB / PuppetDB health on an application host FQDN."""
    base = f"https://{fqdn}:8081"
    simple = await _get_text(client, f"{base}/status/v1/simple")
    services = await _get_json(client, f"{base}/status/v1/services")
    version = await _get_json(client, f"{base}/pdb/meta/v1/version")
    # Lightweight query proves DB path (empty result is fine)
    nodes = await _get_json(client, f"{base}/pdb/query/v4/nodes?limit=1")

    pdb_svc_state = None
    if isinstance(services.get("body"), dict):
        body = services["body"]
        for key, v in body.items():
            if isinstance(v, dict) and ("puppetdb" in str(key).lower() or "status" in v):
                pdb_svc_state = v.get("state") or v.get("status")
                break

    version_str = None
    if isinstance(version.get("body"), dict):
        version_str = version["body"].get("version")

    query_ok = bool(nodes.get("ok"))
    healthy = bool(simple.get("healthy")) and query_ok

    return {
        "fqdn": fqdn,
        "role": "puppetdb",
        "port": 8081,
        "healthy": healthy,
        "simple": simple,
        "services": {
            "ok": services.get("ok"),
            "http_status": services.get("http_status"),
            "error": services.get("error"),
            "state": pdb_svc_state,
        },
        "version": version_str,
        "query_nodes": {
            "ok": query_ok,
            "http_status": nodes.get("http_status"),
            "error": nodes.get("error"),
        },
        "error": None
        if healthy
        else (simple.get("error") or nodes.get("error") or "unhealthy"),
    }


def _parse_pcs_status(text: str) -> Dict[str, Any]:
    """Best-effort parse of ``pcs status`` / ``crm_mon -1`` style text."""
    out: Dict[str, Any] = {
        "raw": text[:8000],
        "online": [],
        "offline": [],
        "resources": [],
        "primary_node": None,
        "vip_node": None,
        "drbd_promoted": None,
        "cluster_name": None,
        "healthy": False,
        "summary": "",
    }
    if not text.strip():
        out["summary"] = "empty pcs output"
        return out

    # Cluster name
    m = re.search(r"Cluster name:\s*(\S+)", text, re.I)
    if m:
        out["cluster_name"] = m.group(1)

    # Online: [ node1 node2 ]
    m = re.search(r"Online:\s*\[([^\]]*)\]", text, re.I)
    if m:
        out["online"] = [x for x in m.group(1).split() if x]
    m = re.search(r"OFFLINE:\s*\[([^\]]*)\]", text, re.I)
    if m:
        out["offline"] = [x for x in m.group(1).split() if x]

    # Promoted / Master (DRBD clone)
    for pat in (
        r"Started:\s*\[?\s*([^\s\]]+).*Promoted",
        r"Promoted:\s*\[?\s*([^\s\]]+)",
        r"Masters:\s*\[?\s*([^\s\]]+)",
        r"\*\s+\w+.*?Promoted\s+([^\s(]+)",
        r"(\S+)\s+Promoted",
    ):
        m = re.search(pat, text, re.I)
        if m:
            out["drbd_promoted"] = m.group(1).strip("[]")
            out["primary_node"] = out["drbd_promoted"]
            break

    # Resources: "* resource_name\t(ocf::...): Started hostname"
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("*") and "Started" not in line and "Promoted" not in line:
            continue
        # * openvox_ca_vip	(ocf::heartbeat:IPaddr2):	 Started ovca1.pdxc...
        rm = re.search(
            r"\*\s+(\S+).*?(?:Started|Promoted|Slave|Master|Unpromoted)\s+(\S+)",
            line,
            re.I,
        )
        if rm:
            res_name, node = rm.group(1), rm.group(2)
            state = "unknown"
            for s in ("Promoted", "Started", "Unpromoted", "Stopped", "FAILED"):
                if s.lower() in line.lower():
                    state = s
                    break
            out["resources"].append({"name": res_name, "state": state, "node": node})
            if "vip" in res_name.lower() or "ipaddr" in line.lower():
                out["vip_node"] = node
            if state == "Promoted":
                out["primary_node"] = node
                out["drbd_promoted"] = node

    # Healthy if we have online nodes and no obvious FAILED
    failed = "FAILED" in text or "failed" in text.lower() and "0 failed" not in text.lower()
    out["healthy"] = bool(out["online"]) and not failed
    if out["primary_node"]:
        out["summary"] = f"primary={out['primary_node']} online={','.join(out['online'])}"
    else:
        out["summary"] = f"online={','.join(out['online']) or 'unknown'}"

    return out


async def _run_cmd(cmd: List[str], timeout: float = 20.0) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


async def probe_ha_cluster(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pacemaker/corosync/DRBD health.

    Prefers local ``pcs status`` (GUI co-located on a CA node). Falls back to
    bolt against the first configured CA FQDN.
    """
    result: Dict[str, Any] = {
        "available": False,
        "method": None,
        "pcs": None,
        "drbd": None,
        "error": None,
    }

    pcs_bin = shutil.which("pcs")
    if pcs_bin:
        pcs_run = await _run_cmd([pcs_bin, "status"], timeout=25.0)
        result["method"] = "local_pcs"
        result["available"] = pcs_run["returncode"] == 0
        if pcs_run["returncode"] == 0:
            result["pcs"] = _parse_pcs_status(pcs_run["stdout"])
        else:
            result["error"] = (pcs_run["stderr"] or pcs_run["stdout"] or "pcs status failed")[
                :500
            ]
            result["pcs"] = _parse_pcs_status(pcs_run["stdout"] or pcs_run["stderr"])

        drbd = shutil.which("drbdadm")
        if drbd:
            drbd_run = await _run_cmd([drbd, "status"], timeout=15.0)
            result["drbd"] = {
                "returncode": drbd_run["returncode"],
                "raw": (drbd_run["stdout"] or drbd_run["stderr"])[:4000],
            }
            # crude primary detect
            m = re.search(r"role:(Primary|Secondary)", drbd_run["stdout"] or "", re.I)
            if m and result.get("pcs") and not result["pcs"].get("primary_node"):
                # can't map host from drbd alone easily
                result["drbd"]["local_role"] = m.group(1)
        return result

    # Remote via Bolt to first CA *member* (not VIP). Inventory is generated
    # under /opt/openvox-gui/data from cluster_config FQDNs — never /etc
    # inventory.yaml (often root-only; fleet targets come from PDB plugin there).
    ca_nodes = list(cfg.get("ca_nodes") or [])
    if not ca_nodes:
        try:
            from .estate_inventory import discover_serving_estate

            ca_nodes = list(discover_serving_estate().get("ca_nodes") or [])
        except Exception:
            ca_nodes = []

    if ca_nodes:
        try:
            from ..routers.bolt_runtime import find_bolt, run_bolt_command

            if find_bolt():
                target = ca_nodes[0]
                bolt_run = await run_bolt_command(
                    [
                        "command",
                        "run",
                        "pcs status 2>&1; echo '---DRBD---'; drbdadm status 2>&1 || true",
                        "--targets",
                        target,
                        "--run-as",
                        "root",
                        "--format",
                        "json",
                    ],
                    timeout=45,
                )
                result["method"] = f"bolt:{target}"
                # Prefer human stdout from bolt item if json wrapper
                out = bolt_run.get("stdout") or bolt_run.get("stderr") or ""
                if out.strip().startswith("{"):
                    try:
                        import json as _json

                        data = _json.loads(out[out.find("{") :])
                        items = data.get("items") or []
                        if items and isinstance(items[0], dict):
                            val = items[0].get("value") or {}
                            out = str(val.get("stdout") or val.get("merged_output") or out)
                    except Exception:
                        pass
                result["available"] = bolt_run.get("returncode") == 0 and bool(
                    (out or "").strip()
                )
                if "---DRBD---" in out:
                    pcs_part, drbd_part = out.split("---DRBD---", 1)
                else:
                    pcs_part, drbd_part = out, ""
                result["pcs"] = _parse_pcs_status(pcs_part)
                result["drbd"] = (
                    {"raw": drbd_part[:4000]} if drbd_part.strip() else None
                )
                if not result["available"]:
                    result["error"] = (
                        bolt_run.get("stderr") or "bolt pcs status failed"
                    )[:500]
                return result
        except Exception as e:
            result["error"] = f"bolt HA probe failed: {e}"[:500]
            # fall through to final message

    result["error"] = (
        result.get("error")
        or (
            "pcs not on this console and Bolt could not reach a CA member. "
            "Configure ca_nodes in Settings → Cluster and ensure bolt SSH "
            "(user bolt) works to those hosts. Static inventory.yaml is not used."
        )
    )
    return result


async def probe_cluster_members(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backward-compatible flat list used by Services UI (summary rows)."""
    full = await probe_cluster_full(cfg)
    rows: List[Dict[str, Any]] = []
    for m in full.get("compilers") or []:
        rows.append(
            {
                "fqdn": m["fqdn"],
                "role": "compiler",
                "port": "8140",
                "healthy": m.get("healthy"),
                "body": (m.get("simple") or {}).get("body"),
                "http_status": (m.get("simple") or {}).get("http_status"),
                "error": m.get("error"),
                "detail": m.get("services"),
            }
        )
    for m in full.get("puppetdb_nodes") or []:
        rows.append(
            {
                "fqdn": m["fqdn"],
                "role": "puppetdb",
                "port": "8081",
                "healthy": m.get("healthy"),
                "body": (m.get("simple") or {}).get("body"),
                "http_status": (m.get("simple") or {}).get("http_status"),
                "error": m.get("error"),
                "version": m.get("version"),
                "query_nodes": m.get("query_nodes"),
            }
        )
    for m in full.get("ca_nodes") or []:
        rows.append(
            {
                "fqdn": m["fqdn"],
                "role": "ca",
                "port": "8140",
                "healthy": m.get("healthy"),
                "body": (m.get("simple") or {}).get("body"),
                "http_status": (m.get("simple") or {}).get("http_status"),
                "error": m.get("error"),
                "detail": m.get("services"),
            }
        )
    return rows


async def probe_gui_console(client: httpx.AsyncClient, fqdn: str) -> Dict[str, Any]:
    """OpenVox GUI health on :4567 (console members / console VIP)."""
    base = f"https://{fqdn}:4567"
    simple = await _get_text(client, f"{base}/health")
    # /health may return JSON {"status":"ok"} — treat 200 as healthy
    healthy = bool(simple.get("healthy")) or simple.get("http_status") == 200
    if not healthy:
        # try without relying on body text "running"
        try:
            r = await client.get(f"{base}/health")
            healthy = r.status_code == 200
            simple = {
                "healthy": healthy,
                "http_status": r.status_code,
                "body": (r.text or "")[:200],
            }
        except Exception as e:
            simple = {"healthy": False, "error": str(e)}
            healthy = False
    return {
        "fqdn": fqdn,
        "role": "console",
        "port": 4567,
        "healthy": healthy,
        "simple": simple,
        "error": simple.get("error") if not healthy else None,
    }


async def probe_cluster_full(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Full estate health document for APIs, UI, and ``ovox infra health``.

    Probes **members and VIPs**:
      - compilers + compiler_vips (8140)
      - puppetdb_nodes + puppetdb_vips (8081)
      - ca_nodes + ca_vips (8140)
      - consoles + console_vips (4567) when provided
    """
    # Prefer expanded inventory when caller passed raw cluster_config only
    compilers = list(cfg.get("compilers") or [])
    compiler_vips = list(cfg.get("compiler_vips") or [])
    pdb_nodes = list(cfg.get("puppetdb_nodes") or [])
    pdb_vips = list(cfg.get("puppetdb_vips") or [])
    ca_nodes = list(cfg.get("ca_nodes") or [])
    ca_vips = list(cfg.get("ca_vips") or [])
    consoles = list(cfg.get("consoles") or [])
    console_vips = list(cfg.get("console_vips") or [])

    if not any([compilers, compiler_vips, pdb_nodes, ca_nodes]):
        try:
            from .estate_inventory import cluster_cfg_for_probes

            expanded = cluster_cfg_for_probes()
            compilers = expanded.get("compilers") or compilers
            compiler_vips = expanded.get("compiler_vips") or compiler_vips
            pdb_nodes = expanded.get("puppetdb_nodes") or pdb_nodes
            pdb_vips = expanded.get("puppetdb_vips") or pdb_vips
            ca_nodes = expanded.get("ca_nodes") or ca_nodes
            ca_vips = expanded.get("ca_vips") or ca_vips
            consoles = expanded.get("consoles") or consoles
            console_vips = expanded.get("console_vips") or console_vips
        except Exception as e:
            logger.debug("estate expand skipped: %s", e)

    verify = _ssl_context()
    timeout = httpx.Timeout(8.0, connect=4.0)

    async with httpx.AsyncClient(
        verify=verify, timeout=timeout, trust_env=False
    ) as client:
        c_tasks = [probe_compiler(client, f) for f in compilers]
        cv_tasks = [probe_compiler(client, f) for f in compiler_vips]
        p_tasks = [probe_puppetdb(client, f) for f in pdb_nodes]
        pv_tasks = [probe_puppetdb(client, f) for f in pdb_vips]
        ca_tasks = [probe_ca(client, f) for f in ca_nodes]
        vip_tasks = [probe_ca(client, f) for f in ca_vips]
        gui_tasks = [probe_gui_console(client, f) for f in consoles]
        guiv_tasks = [probe_gui_console(client, f) for f in console_vips]

        (
            c_res,
            cv_res,
            p_res,
            pv_res,
            ca_res,
            vip_res,
            gui_res,
            guiv_res,
        ) = await asyncio.gather(
            asyncio.gather(*c_tasks) if c_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*cv_tasks) if cv_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*p_tasks) if p_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*pv_tasks) if pv_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*ca_tasks) if ca_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*vip_tasks) if vip_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*gui_tasks) if gui_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*guiv_tasks) if guiv_tasks else asyncio.sleep(0, result=[]),
        )

    # Tag VIP probe results
    def _tag(rows, role: str):
        out = []
        for r in rows or []:
            if isinstance(r, dict):
                rr = dict(r)
                rr["role"] = role
                out.append(rr)
        return out

    ha = await probe_ha_cluster(cfg)

    c_list = list(c_res) if c_res else []
    cv_list = _tag(cv_res, "compiler-vip")
    p_list = list(p_res) if p_res else []
    pv_list = _tag(pv_res, "puppetdb-vip")
    ca_list = list(ca_res) if ca_res else []
    cav_list = _tag(vip_res, "ca-vip")
    gui_list = _tag(gui_res, "console")
    guiv_list = _tag(guiv_res, "console-vip")

    return {
        "deployment_mode": cfg.get("deployment_mode", "single"),
        "compilers": c_list,
        "compiler_vips": cv_list,
        "puppetdb_nodes": p_list,
        "puppetdb_vips": pv_list,
        "ca_nodes": ca_list,
        "ca_vips": cav_list,
        "consoles": gui_list,
        "console_vips": guiv_list,
        "ha": ha,
        "inventory": {
            "compilers": compilers,
            "compiler_vips": compiler_vips,
            "puppetdb_nodes": pdb_nodes,
            "puppetdb_vips": pdb_vips,
            "ca_nodes": ca_nodes,
            "ca_vips": ca_vips,
            "consoles": consoles,
            "console_vips": console_vips,
        },
        "summary": {
            "compilers_healthy": sum(1 for x in c_list if x.get("healthy")),
            "compilers_total": len(compilers),
            "compiler_vips_healthy": sum(1 for x in cv_list if x.get("healthy")),
            "compiler_vips_total": len(compiler_vips),
            "puppetdb_healthy": sum(1 for x in p_list if x.get("healthy")),
            "puppetdb_total": len(pdb_nodes),
            "puppetdb_vips_healthy": sum(1 for x in pv_list if x.get("healthy")),
            "puppetdb_vips_total": len(pdb_vips),
            "ca_healthy": sum(1 for x in ca_list if x.get("healthy")),
            "ca_total": len(ca_nodes),
            "ca_vips_healthy": sum(1 for x in cav_list if x.get("healthy")),
            "ca_vips_total": len(ca_vips),
            "ha_primary": (ha.get("pcs") or {}).get("primary_node"),
            "ha_vip_node": (ha.get("pcs") or {}).get("vip_node"),
            "ha_available": ha.get("available"),
        },
    }
