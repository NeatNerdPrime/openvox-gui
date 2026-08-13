"""
Log Viewer API — Expose system logs without shell access.

Provides read-only access to journalctl output for Puppet/OpenVox-related
services and explicit application log files. All endpoints require admin role.

Commands must match /etc/sudoers.d/openvox-gui-users exactly (see ensure-sudoers.sh).
Argument order is intentional so sudo command matching succeeds.

Tab labels depend on stack flavor (OpenVox packages vs Puppet OSS).
"""
from __future__ import annotations

import logging
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_role
from ..utils.sudo import run_sudo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])

_ADMIN_ONLY = require_role("admin")

# Short TTL so host-picker refresh / auto-refresh does not SSH every 5s
_REMOTE_CACHE: Dict[str, Any] = {}
_REMOTE_CACHE_TS: Dict[str, float] = {}
_REMOTE_CACHE_TTL = 15.0

_SCRIPT = Path("/opt/openvox-gui/scripts/read-logs-remote.py")

# Log sources: journalctl unit(s) AND/OR log file(s) on disk.
# PuppetDB / PuppetServer often prefer file logs; agent is primarily journal.
_LOG_SOURCES: Dict[str, Dict[str, Any]] = {
    "puppet": {
        "unit": "puppet",
        # Some installs use a different unit name; try in order.
        "units": ["puppet", "puppet-agent"],
        # SYSLOG_IDENTIFIER (journalctl -t) — agent process often tags this way
        # even when unit journal is empty or under a different slice.
        "identifiers": ["puppet-agent", "puppet"],
        "files": [
            "/var/log/puppetlabs/puppet/puppet.log",
            "/var/log/puppetlabs/puppet/agent.log",
            "/var/log/puppetlabs/agent/agent.log",
            "/var/log/puppetlabs/puppet/puppet_agent.log",
        ],
        # Agent rarely has on-disk logs; journal first, then host-journal filter.
        "prefer_journal": True,
        "host_journal_fallback": True,
        # Substrings for host-journal line filter (case-insensitive).
        "host_journal_match": (
            "puppet-agent",
            "puppet agent",
            "/puppet/bin/puppet",
            "openvox-agent",
        ),
    },
    "puppetdb": {
        "unit": "puppetdb",
        "units": ["puppetdb"],
        "files": [
            "/var/log/puppetlabs/puppetdb/puppetdb.log",
        ],
    },
    "puppetserver": {
        "unit": "puppetserver",
        "units": ["puppetserver"],
        "files": [
            "/var/log/puppetlabs/puppetserver/puppetserver.log",
        ],
    },
    "openvox-gui": {
        "unit": "openvox-gui",
        "units": ["openvox-gui"],
        "files": [],
    },
    "syslog": {
        "unit": None,
        "units": [],
        "files": [],
        "syslog": True,
    },
}

# Display labels for Log Viewer tabs (source key → label).
_STACK_LABELS = {
    "openvox": {
        "openvox-gui": "OpenVox GUI",
        "puppet": "OpenVox Agent",
        "puppetserver": "OpenVox Server",
        "puppetdb": "OpenVoxDB",
        "syslog": "System Log",
    },
    "puppet": {
        "openvox-gui": "OpenVox GUI",
        "puppet": "Puppet Agent",
        "puppetserver": "PuppetServer",
        "puppetdb": "PuppetDB",
        "syslog": "System Log",
    },
}


def _package_installed(name: str) -> bool:
    """True if rpm or dpkg reports the package as installed."""
    for cmd in (
        ["rpm", "-q", name],
        ["dpkg-query", "-W", "-f=${Status}", name],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                continue
            out = (r.stdout or "").strip().lower()
            if cmd[0] == "dpkg-query":
                if "install ok installed" in out:
                    return True
            else:
                # rpm -q prints package-version when present
                if out and "not installed" not in out:
                    return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def detect_stack_flavor() -> str:
    """
    Return 'openvox' if OpenVox packages are present, else 'puppet' (Puppet OSS).

    Checks agent / server / DB package names used by VoxPupuli OpenVox builds.
    """
    for pkg in ("openvox-agent", "openvox-server", "openvoxdb"):
        if _package_installed(pkg):
            return "openvox"
    # Path/version heuristics when package tools are unavailable
    for marker in (
        Path("/opt/puppetlabs/puppet/lib/ruby/vendor_gems"),
        Path("/opt/puppetlabs/server/apps/puppetserver"),
    ):
        if marker.exists():
            # Look for openvox in release metadata if present
            for rel in Path("/etc").glob("**/openvox*"):
                if rel.is_file() or rel.is_dir():
                    return "openvox"
            break
    try:
        r = subprocess.run(
            ["/opt/puppetlabs/bin/puppet", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        blob = ((r.stdout or "") + (r.stderr or "")).lower()
        if "openvox" in blob:
            return "openvox"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "puppet"


def stack_labels(flavor: Optional[str] = None) -> Dict[str, str]:
    fl = flavor or detect_stack_flavor()
    return dict(_STACK_LABELS.get(fl, _STACK_LABELS["puppet"]))


async def _read_log_file(path: str, lines: int, grep_str: Optional[str] = None) -> list:
    """Read the last N lines from a log file via sudo tail (sudoers-matched argv)."""
    # Skip directories (e.g. some agent builds use puppet_agent.log as a dir)
    try:
        if Path(path).is_dir():
            return []
    except OSError:
        pass
    # Sudoers: /usr/bin/tail -n * <path>
    r = await run_sudo(["sudo", "/usr/bin/tail", "-n", str(lines), path], timeout=15)
    if r["returncode"] != 0:
        err = (r.get("stderr") or "").strip()
        if err and "No such file" not in err and "cannot open" not in err.lower():
            logger.warning("tail %s failed: %s", path, err)
        return []
    stdout = (r.get("stdout") or "").strip()
    result = stdout.split("\n") if stdout else []
    if grep_str:
        grep_lower = grep_str.lower()
        result = [ln for ln in result if grep_lower in ln.lower()]
    return result


async def _read_journal(
    unit: Optional[str] = None,
    lines: int = 200,
    since: Optional[str] = None,
    syslog: bool = False,
    identifier: Optional[str] = None,
) -> Tuple[list, Optional[str]]:
    """
    Read journalctl with argv order fixed to match sudoers:

      journalctl -u <unit> --no-pager -n <N> --output short-iso [--since <spec>]
      journalctl -t <id> --no-pager -n <N> --output short-iso [--since <spec>]
      journalctl --no-pager -n <N> --output short-iso   (syslog / host journal)

    Returns (lines, error_message_or_None).
    """
    if identifier:
        cmd = [
            "sudo",
            "/usr/bin/journalctl",
            "-t",
            identifier,
            "--no-pager",
            "-n",
            str(lines),
            "--output",
            "short-iso",
        ]
        if since:
            cmd.extend(["--since", since])
    elif syslog or unit is None:
        cmd = [
            "sudo",
            "/usr/bin/journalctl",
            "--no-pager",
            "-n",
            str(lines),
            "--output",
            "short-iso",
        ]
        if since:
            cmd.extend(["--since", since])
    else:
        cmd = [
            "sudo",
            "/usr/bin/journalctl",
            "-u",
            unit,
            "--no-pager",
            "-n",
            str(lines),
            "--output",
            "short-iso",
        ]
        if since:
            cmd.extend(["--since", since])

    r = await run_sudo(cmd, timeout=15)
    if r["returncode"] != 0:
        err = (r.get("stderr") or r.get("stdout") or "journalctl failed").strip()
        # Unknown unit/identifier is not always fatal — caller may try another.
        logger.warning(
            "journalctl failed (unit=%s id=%s syslog=%s): %s",
            unit,
            identifier,
            syslog,
            err,
        )
        return [], err

    stdout = (r.get("stdout") or "").strip()
    log_lines = stdout.split("\n") if stdout else []
    log_lines = [ln for ln in log_lines if ln and "-- No entries --" not in ln]
    return log_lines, None


def _filter_host_journal_lines(lines: List[str], matchers: Tuple[str, ...]) -> List[str]:
    """Keep host-journal lines that look like agent output."""
    if not matchers:
        return lines
    lowered = [m.lower() for m in matchers]
    out: List[str] = []
    for ln in lines:
        low = ln.lower()
        if any(m in low for m in lowered):
            out.append(ln)
    return out


async def _collect_source_lines(
    src_config: Dict[str, Any],
    lines: int,
    since: Optional[str],
    grep: Optional[str],
) -> Tuple[list, Optional[str], Optional[str], List[str], Optional[str]]:
    """
    Collect log lines for one source config.

    Returns (log_lines, used_unit, used_file, hard_errors, used_mode).
    used_mode is a short label for debugging (unit / identifier / file / host).
    """
    unit = src_config.get("unit")
    units: List[str] = list(src_config.get("units") or ([unit] if unit else []))
    identifiers: List[str] = list(src_config.get("identifiers") or [])
    log_files: List[str] = list(src_config.get("files") or [])
    if src_config.get("file") and src_config["file"] not in log_files:
        log_files.insert(0, src_config["file"])
    is_syslog = bool(src_config.get("syslog"))
    prefer_journal = bool(src_config.get("prefer_journal"))
    host_fallback = bool(src_config.get("host_journal_fallback"))
    host_match: Tuple[str, ...] = tuple(src_config.get("host_journal_match") or ())

    log_lines: list = []
    hard_errors: list = []
    used_file: Optional[str] = None
    used_unit: Optional[str] = unit
    used_mode: Optional[str] = None

    async def try_files() -> bool:
        nonlocal log_lines, used_file, used_mode
        for log_file in log_files:
            file_lines = await _read_log_file(log_file, lines, grep or None)
            if file_lines:
                log_lines = file_lines
                used_file = log_file
                used_mode = "file"
                return True
        return False

    async def try_unit_journals(since_arg: Optional[str]) -> bool:
        nonlocal log_lines, used_unit, used_mode
        if is_syslog:
            j_lines, j_err = await _read_journal(
                unit=None, lines=lines, since=since_arg, syslog=True
            )
            if j_err:
                hard_errors.append(j_err)
            if j_lines:
                log_lines = j_lines
                used_mode = "syslog"
                return True
            return False
        for u in units:
            j_lines, j_err = await _read_journal(
                unit=u, lines=lines, since=since_arg, syslog=False
            )
            if j_lines:
                log_lines = j_lines
                used_unit = u
                used_mode = f"unit:{u}"
                return True
            if j_err:
                # Only surface real failures (permission / sudoers), not empty units.
                if "No entries" not in j_err and "does not exist" not in j_err.lower():
                    hard_errors.append(f"{u}: {j_err}")
        return False

    async def try_identifiers(since_arg: Optional[str]) -> bool:
        nonlocal log_lines, used_unit, used_mode
        for ident in identifiers:
            j_lines, j_err = await _read_journal(
                identifier=ident, lines=lines, since=since_arg
            )
            if j_lines:
                log_lines = j_lines
                used_unit = ident
                used_mode = f"identifier:{ident}"
                return True
            if j_err and "No entries" not in j_err:
                low = j_err.lower()
                if "permission" in low or "not allowed" in low or "sorry" in low:
                    hard_errors.append(f"-t {ident}: {j_err}")
        return False

    async def try_host_journal(since_arg: Optional[str]) -> bool:
        nonlocal log_lines, used_unit, used_mode
        if not host_fallback:
            return False
        # Pull a wider window from host journal, then filter for agent lines.
        pull_n = min(max(lines * 25, 500), 5000)
        j_lines, j_err = await _read_journal(
            unit=None, lines=pull_n, since=since_arg, syslog=True
        )
        if j_err:
            hard_errors.append(f"host journal: {j_err}")
            return False
        matched = _filter_host_journal_lines(j_lines, host_match)
        if grep:
            g = grep.lower()
            matched = [ln for ln in matched if g in ln.lower()]
        if matched:
            log_lines = matched[-lines:]
            used_unit = "host(filtered)"
            used_mode = "host_journal"
            return True
        return False

    # Order: journal-first for agent; files-first for Server/DB (richer logs).
    if prefer_journal or is_syslog or not log_files:
        if await try_unit_journals(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_identifiers(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_files():
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_host_journal(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode
    else:
        if await try_files():
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_unit_journals(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_identifiers(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode
        if await try_host_journal(since):
            return log_lines, used_unit, used_file, hard_errors, used_mode

    return log_lines, used_unit, used_file, hard_errors, used_mode


def _local_host_names() -> set:
    names: set = set()
    try:
        n = socket.gethostname()
    except OSError:
        n = ""
    if n:
        names.add(n.lower())
        names.add(n.split(".")[0].lower())
    return names


def _is_local_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h or h in ("local", "localhost", "this", "127.0.0.1"):
        return True
    locals_ = _local_host_names()
    if h in locals_:
        return True
    short = h.split(".")[0]
    return short in locals_ or any(h == n or n.startswith(short + ".") for n in locals_)


def _hosts_by_source() -> Tuple[bool, Dict[str, List[Dict[str, str]]]]:
    """Build per-tab host lists from cluster_config. Singleton → empty lists."""
    from ..services.cluster_config import is_clustered, load_cluster_config

    clustered = is_clustered()
    local_label = socket.gethostname() or "this console"
    local_entry = {
        "fqdn": "local",
        "label": f"{local_label} (this console)",
        "transport": "local",
    }
    by_src: Dict[str, List[Dict[str, str]]] = {
        "puppet": [local_entry],
        "syslog": [local_entry],
        "openvox-gui": [dict(local_entry)],
        "puppetserver": [],
        "puppetdb": [],
    }
    if not clustered:
        return False, by_src

    cfg = load_cluster_config()
    for fqdn in cfg.get("compilers") or []:
        by_src["puppetserver"].append(
            {"fqdn": fqdn, "label": fqdn, "transport": "bolt"}
        )
    for fqdn in cfg.get("ca_nodes") or []:
        if fqdn not in {h["fqdn"] for h in by_src["puppetserver"]}:
            by_src["puppetserver"].append(
                {"fqdn": fqdn, "label": f"{fqdn} (CA)", "transport": "bolt"}
            )
    for fqdn in cfg.get("puppetdb_nodes") or []:
        by_src["puppetdb"].append(
            {"fqdn": fqdn, "label": fqdn, "transport": "bolt"}
        )
    locals_ = _local_host_names()
    for fqdn in cfg.get("consoles") or []:
        if fqdn.lower() in locals_ or fqdn.split(".")[0].lower() in locals_:
            continue
        by_src["openvox-gui"].append(
            {"fqdn": fqdn, "label": f"{fqdn} (peer console)", "transport": "bolt"}
        )
    return True, by_src


def _allowed_hosts_for_source(source: str) -> Dict[str, Dict[str, str]]:
    _clustered, by_src = _hosts_by_source()
    return {h["fqdn"].lower(): h for h in (by_src.get(source) or [])}


def _cache_key(source: str, host: str, lines: int, since: Optional[str], grep: Optional[str]) -> str:
    return f"{source}|{host}|{lines}|{since or ''}|{grep or ''}"


async def _fetch_remote_logs(
    source: str,
    host: str,
    lines: int,
    since: Optional[str],
    grep: Optional[str],
) -> Dict[str, Any]:
    from .bolt_runtime import run_bolt_command
    from .deploy import _extract_bolt_json, _script_body

    if not _SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"Missing {_SCRIPT}")

    args = [
        "script",
        "run",
        str(_SCRIPT),
        source,
        "--lines",
        str(lines),
    ]
    if since:
        args.extend(["--since", since])
    if grep:
        args.extend(["--grep", grep])
    args.extend([
        "--targets",
        host,
        "--run-as",
        "root",
        "--format",
        "json",
    ])

    bolt = await run_bolt_command(args, timeout=45)
    data = _extract_bolt_json(bolt.get("stdout") or "")
    item: Dict[str, Any] = {}
    if isinstance(data, dict) and data.get("items"):
        first = data["items"][0]
        item = first if isinstance(first, dict) else {}
    body = (_script_body(item.get("value") or {}) or "").strip()
    parsed: Dict[str, Any] = {}
    if body.startswith("{"):
        import json as _json

        try:
            parsed = _json.loads(body)
        except Exception:
            parsed = {}
    if not parsed:
        err = (bolt.get("stderr") or item.get("value", {}) or {})
        if isinstance(err, dict):
            err = err.get("_error", {}).get("msg") or bolt.get("stderr") or "Bolt returned no log JSON"
        raise HTTPException(
            status_code=502,
            detail=f"Could not read logs on {host}: {err}",
        )
    return parsed


@router.get("/sources")
async def list_sources(_user: str = Depends(_ADMIN_ONLY)):
    """Return available log sources with stack-aware display labels."""
    flavor = detect_stack_flavor()
    labels = stack_labels(flavor)
    sources = []
    for key in _LOG_SOURCES.keys():
        sources.append({
            "id": key,
            "label": labels.get(key, key),
        })
    clustered, hosts_by_source = _hosts_by_source()
    return {
        "stack": flavor,
        "sources": [s["id"] for s in sources],
        "source_meta": sources,
        "labels": labels,
        "clustered": clustered,
        "hosts_by_source": hosts_by_source,
    }


@router.get("/{source}")
async def get_logs(
    source: str,
    lines: int = Query(200, ge=1, le=5000, description="Number of lines to return"),
    since: Optional[str] = Query(None, description="Time filter, e.g. '1h ago', '30m ago', 'today'"),
    grep: Optional[str] = Query(None, description="Filter lines containing this string"),
    host: Optional[str] = Query(None, description="local or allowlisted FQDN (clustered)"),
    _user: str = Depends(_ADMIN_ONLY),
):
    """Fetch recent log lines from journalctl and/or service log files."""
    if source not in _LOG_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown log source '{source}'. Available: {', '.join(_LOG_SOURCES.keys())}",
        )

    src_config = _LOG_SOURCES[source]
    host_raw = (host or "local").strip()
    use_remote = bool(host_raw) and not _is_local_host(host_raw)

    if use_remote:
        allowed = _allowed_hosts_for_source(source)
        key = host_raw.lower()
        if key not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Host {host_raw!r} is not allowed for source '{source}'",
            )
        ck = _cache_key(source, key, lines, since, grep)
        now = time.time()
        hit = _REMOTE_CACHE.get(ck)
        if hit is not None and (now - _REMOTE_CACHE_TS.get(ck, 0)) < _REMOTE_CACHE_TTL:
            return {**hit, "cached": True}
        flavor = detect_stack_flavor()
        labels = stack_labels(flavor)
        try:
            remote = await _fetch_remote_logs(source, host_raw, lines, since, grep)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Remote log fetch failed: {e}")
        payload: Dict[str, Any] = {
            "source": source,
            "label": labels.get(source, source),
            "stack": flavor,
            "host": host_raw,
            "transport": "bolt",
            "unit": remote.get("unit"),
            "file": remote.get("file"),
            "mode": remote.get("mode"),
            "count": len(remote.get("lines") or []),
            "lines": remote.get("lines") or [],
            "cached": False,
        }
        if not payload["lines"] and remote.get("error"):
            payload["error"] = remote["error"]
        elif not payload["lines"]:
            payload["error"] = (
                f"No {labels.get(source, source)} log lines on {host_raw}. "
                "Check journal unit / file path and that bolt can run as root there."
            )
        _REMOTE_CACHE[ck] = payload
        _REMOTE_CACHE_TS[ck] = now
        return payload

    try:
        log_lines, used_unit, used_file, hard_errors, used_mode = await _collect_source_lines(
            src_config, lines, since, grep
        )
        since_relaxed = False

        # Agent is often log_level=err and sparse: a tight "Since" window yields
        # zero lines even though older journal entries exist. If the operator
        # asked for a window and we got nothing, retry without --since and
        # surface the last available agent lines with an explicit note.
        if (
            not log_lines
            and since
            and source == "puppet"
        ):
            log_lines, used_unit, used_file, hard_errors2, used_mode = await _collect_source_lines(
                src_config, lines, None, grep
            )
            hard_errors.extend(hard_errors2)
            if log_lines:
                since_relaxed = True

        if grep and log_lines:
            grep_lower = grep.lower()
            log_lines = [ln for ln in log_lines if grep_lower in ln.lower()]

        flavor = detect_stack_flavor()
        labels = stack_labels(flavor)
        payload: Dict[str, Any] = {
            "source": source,
            "label": labels.get(source, source),
            "stack": flavor,
            "host": "local",
            "transport": "local",
            "unit": used_unit,
            "file": used_file,
            "mode": used_mode,
            "count": len(log_lines),
            "lines": log_lines,
            "cached": False,
        }
        if since_relaxed:
            payload["warning"] = (
                f"No agent log lines in the selected Since window ({since}); "
                "showing last available lines from journal (agent often uses "
                "log_level=err and only writes on failures)."
            )
        if not log_lines:
            hint_parts = list(hard_errors) if hard_errors else []
            if source == "puppet":
                hint_parts.append(
                    "No agent log lines found (journal units puppet/puppet-agent, "
                    "identifiers puppet-agent/puppet, host journal filter, or "
                    "/var/log/puppetlabs/… files). This host’s agent may use "
                    "log_level=err (quiet when healthy), may not have run recently, "
                    "or journal retention may have rotated older entries. "
                    "Try: journalctl -u puppet -n 50; journalctl -t puppet-agent -n 50; "
                    "clear the Since filter in Log Viewer."
                )
            if hint_parts:
                payload["error"] = "; ".join(hint_parts)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
