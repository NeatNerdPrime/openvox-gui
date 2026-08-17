"""
At-a-glance host health for Node Detail (investigation only).

Combines:
  A) Facter snapshot from OpenVoxDB (every live node) — memory, uptime, CPUs, disks
  B) Host Health ring when certname is on the serving estate (console/compiler/PDB/CA)
  C) Optional one-shot live sample via Bolt / local /proc (not fleet-wide collection)

Not used by Dashboard or Nodes list — Node Detail page only.
"""
from __future__ import annotations

import logging
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _local_hostname() -> str:
    try:
        return socket.getfqdn().lower() or socket.gethostname().lower()
    except Exception:
        return "localhost"


def _as_dict(val: Any) -> Dict[str, Any]:
    return val if isinstance(val, dict) else {}


def _first_number(*vals: Any) -> Optional[float]:
    for v in vals:
        if v is None or v == "":
            continue
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(",", "")
        # "15.63 GiB" / "16384.00 MB" / "85.2%"
        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)", s)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _human_bytes(n: Optional[float], unit_hint: str = "B") -> Optional[str]:
    if n is None:
        return None
    try:
        x = float(n)
    except (TypeError, ValueError):
        return None
    # Normalize to bytes
    u = (unit_hint or "B").upper()
    if u in ("KB", "KIB"):
        x *= 1024
    elif u in ("MB", "MIB"):
        x *= 1024**2
    elif u in ("GB", "GIB"):
        x *= 1024**3
    elif u in ("TB", "TIB"):
        x *= 1024**4
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    i = 0
    while x >= 1024 and i < len(units) - 1:
        x /= 1024.0
        i += 1
    if i == 0:
        return f"{int(x)} {units[i]}"
    return f"{x:.1f} {units[i]}"


def facts_to_glance(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize PuppetDB flat fact map into at-a-glance fields.

    Facts may be structured (memory dict) or legacy scalars (memorysize, uptime).
    """
    facts = facts or {}
    mem_block = _as_dict(facts.get("memory"))
    mem_sys = _as_dict(mem_block.get("system"))
    mem_swap = _as_dict(mem_block.get("swap"))

    mem_total = _first_number(
        mem_sys.get("total_bytes"),
        mem_sys.get("total"),
        facts.get("memorysize_mb"),
        facts.get("memorysize"),
    )
    mem_used = _first_number(mem_sys.get("used_bytes"), mem_sys.get("used"), facts.get("memoryfree"))
    mem_avail = _first_number(
        mem_sys.get("available_bytes"),
        mem_sys.get("available"),
        facts.get("memoryfree_mb"),
        facts.get("memoryfree"),
    )
    # memorysize is often a string like "15.63 GiB" — keep display string
    mem_total_str = None
    if isinstance(mem_sys.get("total"), str):
        mem_total_str = mem_sys.get("total")
    elif facts.get("memorysize"):
        mem_total_str = str(facts.get("memorysize"))
    elif mem_sys.get("total_bytes") is not None:
        mem_total_str = _human_bytes(_first_number(mem_sys.get("total_bytes")))

    mem_used_pct: Optional[float] = None
    # Prefer percent from structured facts if present (capacity may be "42.12%")
    if mem_sys.get("capacity") is not None:
        mem_used_pct = _first_number(mem_sys.get("capacity"))
    elif mem_total and mem_avail is not None and mem_total > 0:
        used = mem_total - mem_avail if mem_used is None else mem_used
        mem_used_pct = round(100.0 * (used / mem_total), 1)
    elif mem_total and mem_used is not None and mem_total > 0:
        mem_used_pct = round(100.0 * (mem_used / mem_total), 1)

    # Heuristic: if memorysize_mb style and memoryfree_mb
    mt_mb = _first_number(facts.get("memorysize_mb"))
    mf_mb = _first_number(facts.get("memoryfree_mb"))
    if mem_used_pct is None and mt_mb and mf_mb is not None and mt_mb > 0:
        mem_used_pct = round(100.0 * ((mt_mb - mf_mb) / mt_mb), 1)
        if not mem_total_str:
            mem_total_str = f"{mt_mb:.0f} MiB"

    swap_total_str = None
    swap_used_pct = None
    if mem_swap:
        if isinstance(mem_swap.get("total"), str):
            swap_total_str = mem_swap.get("total")
        st = _first_number(mem_swap.get("total_bytes"), mem_swap.get("total"))
        su = _first_number(mem_swap.get("used_bytes"), mem_swap.get("used"))
        if mem_swap.get("capacity") is not None:
            swap_used_pct = _first_number(mem_swap.get("capacity"))
        elif st and su is not None and st > 0:
            swap_used_pct = round(100.0 * (su / st), 1)

    # Uptime
    su = _as_dict(facts.get("system_uptime"))
    uptime_days = su.get("days")
    uptime_hours = su.get("hours")
    uptime_seconds = _first_number(su.get("seconds"), facts.get("uptime_seconds"))
    uptime_str = facts.get("uptime")
    if not uptime_str and su.get("uptime"):
        uptime_str = su.get("uptime")
    if not uptime_str and uptime_seconds is not None:
        secs = int(uptime_seconds)
        d, r = divmod(secs, 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        parts = []
        if d:
            parts.append(f"{d}d")
        if h or d:
            parts.append(f"{h}h")
        parts.append(f"{m}m")
        uptime_str = " ".join(parts)

    # CPUs
    proc = _as_dict(facts.get("processors"))
    cpu_count = proc.get("count") or facts.get("processorcount") or proc.get("physicalcount")
    cpu_physical = proc.get("physicalcount")
    cpu_models = proc.get("models")
    cpu_model = None
    if isinstance(cpu_models, list) and cpu_models:
        cpu_model = str(cpu_models[0])
    elif isinstance(cpu_models, str):
        cpu_model = cpu_models

    # Disks (block devices)
    disks_block = _as_dict(facts.get("disks"))
    disks: List[Dict[str, Any]] = []
    for name in sorted(disks_block.keys()):
        info = disks_block[name]
        if not isinstance(info, dict):
            continue
        size = info.get("size") or _human_bytes(_first_number(info.get("size_bytes")))
        disks.append({"name": name, "size": size, "model": info.get("model") or info.get("type")})

    # Mountpoints — capacity at a glance (root + largest)
    mps = _as_dict(facts.get("mountpoints"))
    mounts: List[Dict[str, Any]] = []
    for path, info in mps.items():
        if not isinstance(info, dict):
            continue
        # skip pseudo fs
        fs = str(info.get("filesystem") or info.get("device") or "")
        if path.startswith("/sys") or path.startswith("/proc") or path.startswith("/dev"):
            continue
        avail_b = _first_number(info.get("available_bytes"))
        size_b = _first_number(info.get("size_bytes"))
        used_b = _first_number(info.get("used_bytes"))
        cap = _first_number(info.get("capacity"))
        if cap is None and size_b and used_b is not None and size_b > 0:
            cap = round(100.0 * (used_b / size_b), 1)
        mounts.append(
            {
                "path": path,
                "device": info.get("device"),
                "filesystem": info.get("filesystem"),
                "size": info.get("size") or _human_bytes(size_b),
                "available": info.get("available") or _human_bytes(avail_b),
                "used_pct": cap,
            }
        )
    # Prefer / and then highest used %
    mounts.sort(key=lambda m: (0 if m["path"] == "/" else 1, -(m.get("used_pct") or 0)))
    mounts = mounts[:6]

    load_avg = facts.get("load_averages") or facts.get("loadavg")
    load1 = load5 = load15 = None
    if isinstance(load_avg, dict):
        # Facter 4: {"15m": x, "1m": y, "5m": z}
        load1 = _first_number(load_avg.get("1m"), load_avg.get("1"))
        load5 = _first_number(load_avg.get("5m"), load_avg.get("5"))
        load15 = _first_number(load_avg.get("15m"), load_avg.get("15"))
    elif isinstance(load_avg, (list, tuple)) and len(load_avg) >= 1:
        load1 = _first_number(load_avg[0])
        load5 = _first_number(load_avg[1] if len(load_avg) > 1 else None)
        load15 = _first_number(load_avg[2] if len(load_avg) > 2 else None)

    os_block = _as_dict(facts.get("os"))
    os_name = os_block.get("name") or facts.get("operatingsystem")
    os_release = None
    rel = os_block.get("release")
    if isinstance(rel, dict):
        os_release = rel.get("full") or rel.get("major")
    elif isinstance(rel, str):
        os_release = rel
    if not os_release:
        os_release = facts.get("operatingsystemrelease")

    is_virtual = facts.get("is_virtual")
    if is_virtual is None:
        is_virtual = facts.get("virtual") not in (None, "physical", "Physical", False, "false")

    return {
        "as_of_note": "From last agent facts in OpenVoxDB (not a live sample)",
        "memory": {
            "total": mem_total_str,
            "used_pct": mem_used_pct,
            "available": (
                mem_sys.get("available")
                if isinstance(mem_sys.get("available"), str)
                else _human_bytes(mem_avail, "B" if mem_avail and mem_avail > 10000 else "MB")
            ),
            "swap_total": swap_total_str,
            "swap_used_pct": swap_used_pct,
        },
        "uptime": {
            "display": uptime_str,
            "days": uptime_days,
            "hours": uptime_hours,
            "seconds": uptime_seconds,
        },
        "cpu": {
            "count": cpu_count,
            "physical": cpu_physical,
            "model": cpu_model,
        },
        "load": {"load1": load1, "load5": load5, "load15": load15},
        "disks": disks[:12],
        "mounts": mounts,
        "os": {"name": os_name, "release": os_release},
        "virtual": bool(is_virtual) if is_virtual is not None else None,
        "fqdn": facts.get("fqdn") or _as_dict(facts.get("networking")).get("fqdn"),
    }


def _host_keys_for_certname(certname: str) -> List[str]:
    c = (certname or "").strip().lower()
    if not c:
        return []
    keys = [c]
    short = c.split(".")[0]
    if short and short != c:
        keys.append(short)
    return keys


def match_serving_estate(certname: str) -> Tuple[bool, List[str], Optional[str]]:
    """
    Return (is_member, roles, matched_host_key).
    """
    from .host_metrics import serving_estate_targets, _history, _latest, _local_hostname

    keys = set(_host_keys_for_certname(certname))
    local = _local_hostname()
    if local in keys or any(local.startswith(k + ".") or k == local.split(".")[0] for k in keys):
        # cert may be short name of local
        pass

    for t in serving_estate_targets():
        h = (t.get("host") or "").lower()
        h_short = h.split(".")[0]
        if h in keys or h_short in keys or any(k == h or k == h_short or h.endswith("." + k) for k in keys):
            return True, list(t.get("roles") or []), h

    # History may have a key even if roles list drifted
    for k in list(keys) + [local]:
        if k in _latest or k in _history:
            roles: List[str] = []
            for t in serving_estate_targets():
                if (t.get("host") or "").lower() == k:
                    roles = list(t.get("roles") or [])
                    break
            return True, roles, k

    return False, [], None


def estate_snapshot_for(certname: str) -> Optional[Dict[str, Any]]:
    """Cached Host Health latest + history for a certname if estate member."""
    from .host_metrics import _history, _latest, _local_hostname, _load_persisted

    if not _latest and not _history:
        _load_persisted()

    is_member, roles, matched = match_serving_estate(certname)
    if not is_member:
        return None

    local = _local_hostname()
    key = matched or _host_keys_for_certname(certname)[0]
    # Prefer local ring when this is the GUI host
    hist_key = key
    if key == local or key in (local.split(".")[0],) or local.startswith(key + "."):
        hist_key = local if local in _history or local in _latest else key

    latest = _latest.get(hist_key) or _latest.get(key)
    history = list(_history.get(hist_key) or _history.get(key) or [])
    # Try alternate keys
    if not latest and not history:
        for k in _host_keys_for_certname(certname) + [local]:
            if k in _latest or k in _history:
                latest = _latest.get(k)
                history = list(_history.get(k) or [])
                hist_key = k
                break

    return {
        "host": hist_key,
        "roles": roles,
        "is_local": hist_key == local or key == local,
        "latest": latest,
        "history": history[-120:],  # ~30m at 15s — enough for sparklines
    }


async def live_sample(certname: str) -> Dict[str, Any]:
    """One-shot live OS sample (local /proc or Bolt). Does not enable fleet collection."""
    from .host_metrics import (
        collect_local_snapshot,
        collect_remote_via_bolt,
        _store,
        _local_hostname,
    )

    is_member, roles, matched = match_serving_estate(certname)
    local = _local_hostname()
    target = matched or (certname or "").strip().lower()
    keys = _host_keys_for_certname(certname)
    is_local = (
        target == local
        or target in (local.split(".")[0], "localhost", "127.0.0.1")
        or local.split(".")[0] in keys
        or local in keys
    )

    if is_local:
        snap = await collect_local_snapshot()
    else:
        snap = await collect_remote_via_bolt(target)

    # Only persist into Host Health ring when this host is already estate-scoped
    # (keeps agent fleet out of data/host_metrics/).
    if is_member:
        _store(snap)

    return {
        "sample": snap,
        "persisted_to_estate_ring": is_member,
        "roles": roles,
        "target": target,
        "sampled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def build_health_glance(certname: str, facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assemble Node Detail health-glance payload."""
    from .puppetdb import puppetdb_service

    if facts is None:
        facts_raw = await puppetdb_service.get_node_facts(certname)
        facts = {}
        for f in facts_raw or []:
            if isinstance(f, dict) and "name" in f:
                facts[f["name"]] = f.get("value")

    glance = facts_to_glance(facts)
    estate = estate_snapshot_for(certname)
    is_member = estate is not None

    # Light saturation hint from facts when no live estate data
    fact_sat = _fact_saturation_hint(glance)

    return {
        "certname": certname,
        "facts_glance": glance,
        "facts_saturation": fact_sat,
        "serving_estate": {
            "member": is_member,
            "roles": (estate or {}).get("roles") or [],
            "host_key": (estate or {}).get("host"),
            "is_local": (estate or {}).get("is_local", False),
            "latest": (estate or {}).get("latest"),
            "history": (estate or {}).get("history") or [],
        },
        "live_sample_available": True,
        "notes": [
            "Fact gauges reflect the last agent run stored in OpenVoxDB.",
            (
                "Serving-estate sparklines use Host Health history (console/compiler/OpenVoxDB/CA)."
                if is_member
                else "This node is not on the Host Health serving estate — sparklines appear after a live sample (not retained for agents)."
            ),
            "Live sample uses local /proc or Bolt once; it does not enable fleet-wide collection.",
        ],
    }


def _fact_saturation_hint(glance: Dict[str, Any]) -> Dict[str, Any]:
    """Green/yellow/red from fact snapshot only (conservative)."""
    level = "green"
    reasons: List[str] = []

    def bump(new: str, reason: str):
        nonlocal level
        order = {"green": 0, "yellow": 1, "red": 2}
        if order[new] > order[level]:
            level = new
        reasons.append(reason)

    mem = (glance.get("memory") or {}).get("used_pct")
    if mem is not None:
        if mem >= 95:
            bump("red", f"memory {mem}% (facts)")
        elif mem >= 85:
            bump("yellow", f"memory {mem}% (facts)")

    for m in glance.get("mounts") or []:
        pct = m.get("used_pct")
        path = m.get("path") or "?"
        if pct is None:
            continue
        if pct >= 95:
            bump("red", f"{path} {pct}% full")
        elif pct >= 85:
            bump("yellow", f"{path} {pct}% used")

    return {"level": level, "reasons": reasons, "source": "facts"}
