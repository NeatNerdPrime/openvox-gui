"""
Read puppetserver / OpenVoxDB tuning settings on remote estate hosts via Bolt.

Dedicated consoles have no local /etc/puppetlabs/puppetserver|puppetdb.
Settings → Cluster FQDNs + bolt SSH (user bolt) are the source of truth.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_JRUBY_RE = re.compile(r"max-active-instances\s*[:=]\s*(\d+)", re.I)
# Allow optional space: -Xmx 4g
_XMX_RE = re.compile(r"-Xmx\s*(\d+)\s*([gGmMkK]?)")
_XMS_RE = re.compile(r"-Xms\s*(\d+)\s*([gGmMkK]?)")
_CODE_CACHE_RE = re.compile(
    r"-XX:ReservedCodeCacheSize\s*=\s*(\d+)\s*([gGmMkK]?)", re.I
)
# INI pools may use spaces around =
_POOL_RE = re.compile(
    r"\[(read[_-]?pool|write[_-]?pool)\](.*?)(?=\n\[|\Z)",
    re.I | re.S,
)
_MAX_CONN_RE = re.compile(r"max[_-]?connections\s*=\s*(\d+)", re.I)


def _unit_size(num: str, unit: str) -> str:
    u = (unit or "m").lower() or "m"
    if u == "k":
        return f"{num}k"
    return f"{num}{u}"


def _parse_bolt_stdout(bolt: Dict[str, Any]) -> str:
    out = bolt.get("stdout") or ""
    text = str(out)
    # Bolt --format json wraps items[]; also tolerate leading noise
    if "{" not in text:
        return text
    try:
        data = json.loads(text[text.find("{") :])
        items = data.get("items") or []
        chunks: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            val = it.get("value") if isinstance(it.get("value"), dict) else {}
            chunk = str(val.get("stdout") or val.get("merged_output") or "")
            if chunk.strip():
                chunks.append(chunk)
            err = val.get("_error")
            if isinstance(err, dict) and err.get("msg"):
                chunks.append(f"ERROR: {err.get('msg')}")
        if chunks:
            return "\n".join(chunks)
    except Exception:
        pass
    return text


async def bolt_cat_remote(host: str, paths: List[str], timeout: int = 45) -> Dict[str, Any]:
    """Cat conf files on *host* as root via Bolt."""
    from ..routers.bolt_runtime import find_bolt, run_bolt_command

    if not find_bolt():
        return {"host": host, "ok": False, "error": "bolt not installed on console"}

    quoted = " ".join(f'"{p}"' for p in paths)
    # Prefer openvox-server sysconfig name if present
    cmd = (
        f"set +e; "
        f"for f in {quoted}; do "
        f'  echo "===== $f ====="; '
        f'  if [ -r "$f" ]; then cat "$f"; else echo "(missing or unreadable)"; fi; '
        f"done"
    )
    bolt = await run_bolt_command(
        [
            "command",
            "run",
            cmd,
            "--targets",
            host,
            "--run-as",
            "root",
            "--format",
            "json",
        ],
        timeout=timeout,
    )
    text = _parse_bolt_stdout(bolt)
    rc = bolt.get("returncode")
    # Success if we got file markers even when some paths missing
    ok = bool(text.strip()) and "=====" in text and "ERROR:" not in text[:80]
    if rc not in (0, None) and not ok:
        ok = False
    err = ""
    if not ok:
        err = (bolt.get("stderr") or text or f"bolt rc={rc}")[:500]
    return {
        "host": host,
        "ok": ok,
        "stdout": text,
        "error": err,
        "returncode": rc,
    }


def parse_jvm_from_text(text: str) -> Dict[str, Any]:
    """Normalize to heap_min / heap_max / reserved_code_cache (CLI keys)."""
    jvm: Dict[str, Any] = {
        "heap_min": None,
        "heap_max": None,
        "reserved_code_cache": None,
        "raw": None,
    }
    xmx = _XMX_RE.search(text or "")
    xms = _XMS_RE.search(text or "")
    cc = _CODE_CACHE_RE.search(text or "")
    if xms:
        jvm["heap_min"] = _unit_size(xms.group(1), xms.group(2) or "g")
    if xmx:
        jvm["heap_max"] = _unit_size(xmx.group(1), xmx.group(2) or "g")
    if cc:
        jvm["reserved_code_cache"] = _unit_size(cc.group(1), cc.group(2) or "m")
    # Keep a short raw JAVA_ARGS snippet if present
    for line in (text or "").splitlines():
        if "JAVA_ARGS" in line.upper():
            jvm["raw"] = line.strip()[:300]
            break
    return jvm


def parse_puppetserver_snippet(text: str) -> Dict[str, Any]:
    jruby = None
    m = _JRUBY_RE.search(text or "")
    if m:
        jruby = int(m.group(1))
    jvm = parse_jvm_from_text(text or "")
    return {"jruby_max_active_instances": jruby, "jvm": jvm}


def parse_puppetdb_snippet(text: str) -> Dict[str, Any]:
    pools: Dict[str, Optional[int]] = {"read": None, "write": None}
    for m in _POOL_RE.finditer(text or ""):
        section = m.group(1).lower()
        body = m.group(2) or ""
        cm = _MAX_CONN_RE.search(body)
        if not cm:
            continue
        if "read" in section:
            pools["read"] = int(cm.group(1))
        elif "write" in section:
            pools["write"] = int(cm.group(1))
    # Also plain max_connections under [database]
    if pools["read"] is None and pools["write"] is None:
        for m in re.finditer(
            r"max[_-]?connections\s*=\s*(\d+)", text or "", re.I
        ):
            pools["read"] = pools["write"] = int(m.group(1))
            break
    jvm = parse_jvm_from_text(text or "")
    return {"pools": pools, "jvm": jvm}


def _has_usable_ps(sample: Optional[Dict]) -> bool:
    if not sample:
        return False
    if sample.get("jruby_max_active_instances") is not None:
        return True
    jvm = sample.get("jvm") or {}
    return bool(jvm.get("heap_max") or jvm.get("heap_min"))


def _has_usable_pdb(sample: Optional[Dict]) -> bool:
    if not sample:
        return False
    pools = sample.get("pools") or {}
    if pools.get("read") is not None or pools.get("write") is not None:
        return True
    jvm = sample.get("jvm") or {}
    return bool(jvm.get("heap_max") or jvm.get("heap_min"))


async def sample_remote_infra_settings() -> Dict[str, Any]:
    """Bolt-read settings from compilers and OpenVoxDB members (try several)."""
    from .estate_inventory import discover_serving_estate

    est = discover_serving_estate()
    out: Dict[str, Any] = {
        "method": "bolt",
        "puppetserver": {"hosts": [], "sample": None},
        "puppetdb": {"hosts": [], "sample": None},
        "errors": [],
        "tried": {"compilers": [], "puppetdb_nodes": []},
    }

    compilers = list(est.get("compilers") or [])
    # Fall back to compiler VIP only if no members (last resort)
    if not compilers:
        compilers = list(est.get("compiler_vips") or [])
        if compilers:
            out["errors"].append(
                "No compiler members in cluster config; trying compiler VIP(s). "
                "Add ovcompiler1/2 FQDNs under Settings → Cluster."
            )
    pdbs = list(est.get("puppetdb_nodes") or [])
    if not pdbs:
        pdbs = list(est.get("puppetdb_vips") or [])
        if pdbs:
            out["errors"].append(
                "No OpenVoxDB members in cluster config; trying PDB VIP. "
                "Add ovdb node FQDNs under Settings → Cluster."
            )

    out["tried"]["compilers"] = compilers[:6]
    out["tried"]["puppetdb_nodes"] = pdbs[:6]

    if not compilers and not pdbs:
        out["errors"].append(
            "No remote hosts to sample. Configure compilers and puppetdb_nodes "
            "in Settings → Application → Cluster, ensure bolt SSH (user bolt) works."
        )
        return out

    ps_paths = [
        "/etc/puppetlabs/puppetserver/conf.d/puppetserver.conf",
        "/etc/sysconfig/puppetserver",
        "/etc/sysconfig/openvox-server",
    ]
    pdb_paths = [
        "/etc/puppetlabs/puppetdb/conf.d/database.ini",
        "/etc/sysconfig/puppetdb",
        "/etc/sysconfig/openvoxdb",
    ]

    for host in compilers[:6]:
        r = await bolt_cat_remote(host, ps_paths)
        entry: Dict[str, Any] = {
            "host": host,
            "ok": r.get("ok"),
            "error": r.get("error"),
        }
        if r.get("ok"):
            parsed = parse_puppetserver_snippet(r.get("stdout") or "")
            entry.update(parsed)
            if not _has_usable_ps(out["puppetserver"]["sample"]) and (
                parsed.get("jruby_max_active_instances") is not None
                or (parsed.get("jvm") or {}).get("heap_max")
            ):
                out["puppetserver"]["sample"] = {"host": host, **parsed}
        else:
            out["errors"].append(f"compiler {host}: {r.get('error') or 'bolt failed'}")
        out["puppetserver"]["hosts"].append(entry)
        if _has_usable_ps(out["puppetserver"]["sample"]):
            break

    for host in pdbs[:6]:
        r = await bolt_cat_remote(host, pdb_paths)
        entry = {"host": host, "ok": r.get("ok"), "error": r.get("error")}
        if r.get("ok"):
            parsed = parse_puppetdb_snippet(r.get("stdout") or "")
            entry.update(parsed)
            if not _has_usable_pdb(out["puppetdb"]["sample"]) and (
                (parsed.get("pools") or {}).get("read") is not None
                or (parsed.get("jvm") or {}).get("heap_max")
            ):
                out["puppetdb"]["sample"] = {"host": host, **parsed}
        else:
            out["errors"].append(f"puppetdb {host}: {r.get('error') or 'bolt failed'}")
        out["puppetdb"]["hosts"].append(entry)
        if _has_usable_pdb(out["puppetdb"]["sample"]):
            break

    if compilers and not _has_usable_ps(out["puppetserver"]["sample"]):
        out["errors"].append(
            "Could not parse puppetserver settings from any compiler "
            "(bolt SSH / sudo root / conf paths)."
        )
    if pdbs and not _has_usable_pdb(out["puppetdb"]["sample"]):
        out["errors"].append(
            "Could not parse OpenVoxDB pool/JVM settings from any ovdb host."
        )

    return out
