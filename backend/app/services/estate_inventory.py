"""
Serving-estate host inventory for health probes and Host Health.

Builds the full list of **member** FQDNs and **VIP/LB** FQDNs from:
  - cluster_config.json (compilers, puppetdb_nodes, ca_nodes, ca_vips,
    infra_vips, consoles, vip_hosts, code_deploy_targets)
  - OPENVOX_GUI_* settings (puppet_server_host, puppet_ca_host, puppetdb_host)
  - local console hostname

Used by ``ovox infra health`` so operators see every compiler and every VIP,
not only the single server_urls VIP from .env.
"""
from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Set, Tuple

from ..config import settings

logger = logging.getLogger(__name__)


def _norm(name: str) -> str:
    return (name or "").strip().lower().split(":")[0]


def _local_names() -> Set[str]:
    out: Set[str] = {"localhost", "127.0.0.1", "::1"}
    try:
        out.add(socket.gethostname().lower())
        out.add(socket.getfqdn().lower())
    except OSError:
        pass
    return out


def discover_serving_estate() -> Dict[str, Any]:
    """Return de-duplicated estate members and VIPs by role.

    Shape::

        {
          "deployment_mode": "single"|"clustered",
          "compilers": [...],          # member FQDNs
          "compiler_vips": [...],      # LB names (not also members)
          "puppetdb_nodes": [...],
          "puppetdb_vips": [...],
          "ca_nodes": [...],
          "ca_vips": [...],
          "consoles": [...],
          "console_vips": [...],
          "all_probe_targets": [       # flat list for callers
             {"fqdn": "...", "role": "compiler"|"compiler-vip"|..., "kind": "member"|"vip"},
             ...
          ],
        }
    """
    from .cluster_config import load_cluster_config

    cfg = load_cluster_config()
    mode = cfg.get("deployment_mode") or "single"

    compilers: Set[str] = set()
    compiler_vips: Set[str] = set()
    pdb_nodes: Set[str] = set()
    pdb_vips: Set[str] = set()
    ca_nodes: Set[str] = set()
    ca_vips: Set[str] = set()
    consoles: Set[str] = set()
    console_vips: Set[str] = set()

    def _add_list(raw, bucket: Set[str]) -> None:
        for item in raw or []:
            n = _norm(str(item))
            if n and n not in _local_names() | {"0.0.0.0"}:
                bucket.add(n)

    _add_list(cfg.get("compilers"), compilers)
    _add_list(cfg.get("code_deploy_targets"), compilers)
    _add_list(cfg.get("puppetdb_nodes"), pdb_nodes)
    _add_list(cfg.get("ca_nodes"), ca_nodes)
    _add_list(cfg.get("ca_vips"), ca_vips)
    _add_list(cfg.get("consoles"), consoles)
    _add_list(cfg.get("vip_hosts"), console_vips)
    # infra_vips = compiler/PDB LBs (HAProxy/DNS)
    _add_list(cfg.get("infra_vips"), compiler_vips)

    # App .env VIPs / primary endpoints
    ps = _norm(getattr(settings, "puppet_server_host", "") or "")
    if ps and ps not in ("localhost", "127.0.0.1"):
        if ps in compilers:
            pass
        else:
            compiler_vips.add(ps)

    ca = _norm(getattr(settings, "puppet_ca_host", "") or "")
    if ca and ca not in ("localhost", "127.0.0.1"):
        if ca in ca_nodes:
            pass
        else:
            ca_vips.add(ca)

    pdb = _norm(getattr(settings, "puppetdb_host", "") or "")
    if pdb and pdb not in ("localhost", "127.0.0.1"):
        if pdb in pdb_nodes:
            pass
        else:
            pdb_vips.add(pdb)

    # Local console
    for n in _local_names():
        if n not in ("localhost", "127.0.0.1", "::1", "0.0.0.0") and "." in n:
            consoles.add(n)

    # VIP sets should not duplicate members
    compiler_vips -= compilers
    pdb_vips -= pdb_nodes
    ca_vips -= ca_nodes
    console_vips -= consoles

    targets: List[Dict[str, str]] = []

    def _emit(hosts: Set[str], role: str, kind: str) -> None:
        for h in sorted(hosts):
            targets.append({"fqdn": h, "role": role, "kind": kind})

    _emit(compilers, "compiler", "member")
    _emit(compiler_vips, "compiler-vip", "vip")
    _emit(pdb_nodes, "puppetdb", "member")
    _emit(pdb_vips, "puppetdb-vip", "vip")
    _emit(ca_nodes, "ca", "member")
    _emit(ca_vips, "ca-vip", "vip")
    _emit(consoles, "console", "member")
    _emit(console_vips, "console-vip", "vip")

    return {
        "deployment_mode": mode,
        "compilers": sorted(compilers),
        "compiler_vips": sorted(compiler_vips),
        "puppetdb_nodes": sorted(pdb_nodes),
        "puppetdb_vips": sorted(pdb_vips),
        "ca_nodes": sorted(ca_nodes),
        "ca_vips": sorted(ca_vips),
        "consoles": sorted(consoles),
        "console_vips": sorted(console_vips),
        "all_probe_targets": targets,
    }


def cluster_cfg_for_probes() -> Dict[str, Any]:
    """cluster_config-shaped dict expanded with settings VIPs for probe_cluster_full."""
    from .cluster_config import load_cluster_config

    base = dict(load_cluster_config())
    est = discover_serving_estate()
    base["compilers"] = est["compilers"]
    base["puppetdb_nodes"] = est["puppetdb_nodes"]
    base["ca_nodes"] = est["ca_nodes"]
    base["ca_vips"] = est["ca_vips"]
    # Extra keys consumed by expanded probe_cluster_full
    base["compiler_vips"] = est["compiler_vips"]
    base["puppetdb_vips"] = est["puppetdb_vips"]
    base["consoles"] = est["consoles"]
    base["console_vips"] = est["console_vips"]
    return base
