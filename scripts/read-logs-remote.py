#!/usr/bin/env python3
"""Read OpenVox / Puppet service logs on this host (journalctl and/or tail).

Used by openvox-gui Log Viewer over Bolt on compilers, OpenVoxDB, and peer
consoles. Prints one JSON object on stdout.

Usage:
  read-logs-remote.py <source> [--lines N] [--since SPEC] [--grep TEXT]

Sources: puppetserver, puppetdb, openvox-gui, puppet, syslog
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCES = {
    "puppetserver": {
        "units": ["puppetserver"],
        "files": ["/var/log/puppetlabs/puppetserver/puppetserver.log"],
        "prefer_journal": False,
    },
    "puppetdb": {
        "units": ["puppetdb"],
        "files": ["/var/log/puppetlabs/puppetdb/puppetdb.log"],
        "prefer_journal": False,
    },
    "openvox-gui": {
        "units": ["openvox-gui"],
        "files": [],
        "prefer_journal": True,
    },
    "puppet": {
        "units": ["puppet", "puppet-agent"],
        "files": [
            "/var/log/puppetlabs/puppet/puppet.log",
            "/var/log/puppetlabs/puppet/agent.log",
        ],
        "prefer_journal": True,
    },
    "syslog": {
        "units": [],
        "files": [],
        "syslog": True,
    },
}


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def _journal(unit: str | None, lines: int, since: str | None, syslog: bool) -> list[str]:
    if syslog or not unit:
        cmd = ["/usr/bin/journalctl", "--no-pager", "-n", str(lines), "--output", "short-iso"]
    else:
        cmd = [
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
    rc, out, _err = _run(cmd)
    if rc != 0 or not out.strip():
        return []
    return [ln for ln in out.splitlines() if ln and "-- No entries --" not in ln]


def _tail(path: str, lines: int) -> list[str]:
    p = Path(path)
    if not p.is_file():
        return []
    rc, out, _err = _run(["/usr/bin/tail", "-n", str(lines), path])
    if rc != 0 or not out.strip():
        return []
    return out.splitlines()


def collect(source: str, lines: int, since: str | None, grep: str | None) -> dict:
    cfg = SOURCES[source]
    used_mode = None
    used_unit = None
    used_file = None
    log_lines: list[str] = []

    if cfg.get("syslog"):
        log_lines = _journal(None, lines, since, True)
        used_mode = "syslog" if log_lines else None
    else:
        files = list(cfg.get("files") or [])
        units = list(cfg.get("units") or [])
        prefer_journal = bool(cfg.get("prefer_journal"))

        def try_files() -> bool:
            nonlocal log_lines, used_file, used_mode
            for f in files:
                got = _tail(f, lines)
                if got:
                    log_lines, used_file, used_mode = got, f, "file"
                    return True
            return False

        def try_journal() -> bool:
            nonlocal log_lines, used_unit, used_mode
            for u in units:
                got = _journal(u, lines, since, False)
                if got:
                    log_lines, used_unit, used_mode = got, u, f"unit:{u}"
                    return True
            return False

        if prefer_journal or not files:
            try_journal() or try_files()
        else:
            try_files() or try_journal()

    if grep and log_lines:
        g = grep.lower()
        log_lines = [ln for ln in log_lines if g in ln.lower()]

    host = os.uname().nodename if hasattr(os, "uname") else ""
    return {
        "source": source,
        "host": host,
        "lines": log_lines,
        "count": len(log_lines),
        "unit": used_unit,
        "file": used_file,
        "mode": used_mode,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("source", choices=sorted(SOURCES.keys()))
    p.add_argument("--lines", type=int, default=200)
    p.add_argument("--since", default="")
    p.add_argument("--grep", default="")
    args = p.parse_args()
    lines = max(1, min(int(args.lines or 200), 5000))
    since = (args.since or "").strip() or None
    grep = (args.grep or "").strip() or None
    payload = collect(args.source, lines, since, grep)
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
