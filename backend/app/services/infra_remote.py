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

_JRUBY_RE = re.compile(
    r"max-active-instances\s*[:=]\s*(\d+)", re.I
)
_XMX_RE = re.compile(r"-Xmx(\d+)([gGmM]?)")
_XMS_RE = re.compile(r"-Xms(\d+)([gGmM]?)")
_POOL_RE = re.compile(
    r"\[(read_pool|write_pool)\][^\[]*?max_connections\s*=\s*(\d+)",
    re.I | re.S,
)


def _parse_bolt_stdout(bolt: Dict[str, Any]) -> str:
    out = bolt.get("stdout") or ""
    if not str(out).strip().startswith("{"):
        return str(out)
    try:
        data = json.loads(str(out)[str(out).find("{") :])
        items = data.get("items") or []
        if items and isinstance(items[0], dict):
            val = items[0].get("value") or {}
            return str(val.get("stdout") or val.get("merged_output") or out)
    except Exception:
        pass
    return str(out)


async def bolt_cat_remote(host: str, paths: List[str], timeout: int = 40) -> Dict[str, Any]:
    """Run a small shell snippet on *host* via Bolt; return stdout/error."""
    from ..routers.bolt_runtime import find_bolt, run_bolt_command

    if not find_bolt():
        return {"host": host, "ok": False, "error": "bolt not installed on console"}
    # quote paths
    quoted = " ".join(f"'{p}'" for p in paths)
    cmd = f"for f in {quoted}; do echo \"===== $f =====\"; cat \"$f\" 2>/dev/null || echo '(missing)'; done"
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
    ok = bolt.get("returncode") == 0 and bool(text.strip())
    err = ""
    if not ok:
        err = (bolt.get("stderr") or text or "bolt command failed")[:400]
    return {"host": host, "ok": ok, "stdout": text, "error": err, "returncode": bolt.get("returncode")}


def parse_puppetserver_snippet(text: str) -> Dict[str, Any]:
    jruby = None
    m = _JRUBY_RE.search(text or "")
    if m:
        jruby = int(m.group(1))
    xmx = _XMX_RE.search(text or "")
    xms = _XMS_RE.search(text or "")
    jvm: Dict[str, Any] = {}
    if xmx:
        jvm["xmx"] = xmx.group(0)
    if xms:
        jvm["xms"] = xms.group(0)
    return {"jruby_max_active_instances": jruby, "jvm": jvm}


def parse_puppetdb_snippet(text: str) -> Dict[str, Any]:
    pools: Dict[str, Optional[int]] = {"read": None, "write": None}
    for m in _POOL_RE.finditer(text or ""):
        key = "read" if "read" in m.group(1).lower() else "write"
        pools[key] = int(m.group(2))
    xmx = _XMX_RE.search(text or "")
    jvm: Dict[str, Any] = {}
    if xmx:
        jvm["xmx"] = xmx.group(0)
    return {"pools": pools, "jvm": jvm}


async def sample_remote_infra_settings() -> Dict[str, Any]:
    """Bolt-read settings from first reachable compiler and OpenVoxDB member."""
    from .estate_inventory import discover_serving_estate

    est = discover_serving_estate()
    out: Dict[str, Any] = {
        "method": "bolt",
        "puppetserver": {"hosts": [], "sample": None},
        "puppetdb": {"hosts": [], "sample": None},
        "errors": [],
    }

    compilers = list(est.get("compilers") or [])
    pdbs = list(est.get("puppetdb_nodes") or [])

    for host in compilers[:4]:  # sample up to 4
        r = await bolt_cat_remote(
            host,
            [
                "/etc/puppetlabs/puppetserver/conf.d/puppetserver.conf",
                "/etc/sysconfig/puppetserver",
            ],
        )
        entry = {"host": host, "ok": r.get("ok"), "error": r.get("error")}
        if r.get("ok"):
            parsed = parse_puppetserver_snippet(r.get("stdout") or "")
            entry.update(parsed)
            if out["puppetserver"]["sample"] is None:
                out["puppetserver"]["sample"] = {"host": host, **parsed}
        out["puppetserver"]["hosts"].append(entry)
        if r.get("ok") and out["puppetserver"]["sample"]:
            break  # one good sample is enough for display
        if r.get("error"):
            out["errors"].append(f"{host}: {r.get('error')}")

    for host in pdbs[:4]:
        r = await bolt_cat_remote(
            host,
            [
                "/etc/puppetlabs/puppetdb/conf.d/database.ini",
                "/etc/sysconfig/puppetdb",
            ],
        )
        entry = {"host": host, "ok": r.get("ok"), "error": r.get("error")}
        if r.get("ok"):
            parsed = parse_puppetdb_snippet(r.get("stdout") or "")
            entry.update(parsed)
            if out["puppetdb"]["sample"] is None:
                out["puppetdb"]["sample"] = {"host": host, **parsed}
        out["puppetdb"]["hosts"].append(entry)
        if r.get("ok") and out["puppetdb"]["sample"]:
            break
        if r.get("error"):
            out["errors"].append(f"{host}: {r.get('error')}")

    return out
