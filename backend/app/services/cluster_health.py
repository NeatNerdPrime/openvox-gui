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

    # Remote via bolt to first CA node
    ca_nodes = cfg.get("ca_nodes") or []
    bolt = shutil.which("bolt")
    if bolt and ca_nodes:
        target = ca_nodes[0]
        bolt_cmd = [
            bolt,
            "command",
            "run",
            "pcs status 2>&1; echo '---DRBD---'; drbdadm status 2>&1 || true",
            "--targets",
            target,
            "--no-host-key-check",
        ]
        inv = Path("/etc/puppetlabs/bolt/inventory.yaml")
        if inv.exists():
            bolt_cmd.extend(["-i", str(inv)])
        bolt_run = await _run_cmd(bolt_cmd, timeout=45.0)
        result["method"] = f"bolt:{target}"
        out = bolt_run["stdout"] or bolt_run["stderr"]
        result["available"] = bolt_run["returncode"] == 0 and bool(out.strip())
        if "---DRBD---" in out:
            pcs_part, drbd_part = out.split("---DRBD---", 1)
        else:
            pcs_part, drbd_part = out, ""
        result["pcs"] = _parse_pcs_status(pcs_part)
        result["drbd"] = {"raw": drbd_part[:4000]} if drbd_part.strip() else None
        if not result["available"]:
            result["error"] = (bolt_run["stderr"] or "bolt pcs status failed")[:500]
        return result

    result["error"] = (
        "pcs not found on this host and no bolt+ca_nodes for remote status. "
        "Install pcs on the GUI host (if co-located with CA) or configure ca_nodes "
        "and bolt inventory."
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


async def probe_cluster_full(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Full clustered health document for APIs and UI."""
    compilers = cfg.get("compilers") or []
    pdb_nodes = cfg.get("puppetdb_nodes") or []
    ca_nodes = cfg.get("ca_nodes") or []
    ca_vips = cfg.get("ca_vips") or []

    verify = _ssl_context()
    # verify=False fallback only if CA file missing — still try mTLS context
    timeout = httpx.Timeout(8.0, connect=4.0)

    async with httpx.AsyncClient(
        verify=verify, timeout=timeout, trust_env=False
    ) as client:
        c_tasks = [probe_compiler(client, f) for f in compilers]
        p_tasks = [probe_puppetdb(client, f) for f in pdb_nodes]
        ca_tasks = [probe_ca(client, f) for f in ca_nodes]
        vip_tasks = [probe_ca(client, f) for f in ca_vips]

        c_res, p_res, ca_res, vip_res = await asyncio.gather(
            asyncio.gather(*c_tasks) if c_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*p_tasks) if p_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*ca_tasks) if ca_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*vip_tasks) if vip_tasks else asyncio.sleep(0, result=[]),
        )

    ha = await probe_ha_cluster(cfg)

    return {
        "deployment_mode": cfg.get("deployment_mode", "single"),
        "compilers": list(c_res) if c_res else [],
        "puppetdb_nodes": list(p_res) if p_res else [],
        "ca_nodes": list(ca_res) if ca_res else [],
        "ca_vips": list(vip_res) if vip_res else [],
        "ha": ha,
        "summary": {
            "compilers_healthy": sum(1 for x in (c_res or []) if x.get("healthy")),
            "compilers_total": len(compilers),
            "puppetdb_healthy": sum(1 for x in (p_res or []) if x.get("healthy")),
            "puppetdb_total": len(pdb_nodes),
            "ca_healthy": sum(1 for x in (ca_res or []) if x.get("healthy")),
            "ca_total": len(ca_nodes),
            "ha_primary": (ha.get("pcs") or {}).get("primary_node"),
            "ha_vip_node": (ha.get("pcs") or {}).get("vip_node"),
            "ha_available": ha.get("available"),
        },
    }
