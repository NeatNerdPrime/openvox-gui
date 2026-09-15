"""Jolokia ObjectName escaping and HTTP bean selection (no PuppetDB client)."""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple


def unescape_jolokia_mbean(name: str) -> str:
    """POST ObjectNames use real slashes; !/ is only a GET path escape."""
    return (name or "").replace("!/", "/")


def escape_jolokia_path(name: str) -> str:
    """Escape / as !/ for Jolokia GET paths without double-escaping."""
    return re.sub(r"(?<!!)/", "!/", name or "")


def normalize_mbean(name: str) -> str:
    return unescape_jolokia_mbean(name).lower()


def jolokia_row_value(row: Any) -> Any:
    """Return the metric payload, or None for 404 / error rows."""
    if not isinstance(row, dict):
        return None
    if row.get("error"):
        return None
    status = row.get("status")
    if status not in (None, 200):
        return None
    if "value" in row:
        return row.get("value")
    return None


def timer_present(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, dict):
        if val.get("error"):
            return False
        return any(
            isinstance(val.get(k), (int, float)) and not isinstance(val.get(k), bool)
            for k in ("Mean", "mean", "Value", "value", "Count")
        )
    return False


def pick_http_latency_beans(beans: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Pick query + command service-time beans from a Jolokia search list."""
    service = [b for b in beans if "service-time" in b.lower()]
    query = None
    cmd = None
    for hint in ("/pdb/query/v4", "/pdb/query", "query.service-time"):
        query = next((b for b in service if hint in b), None)
        if query:
            break
    for hint in ("/pdb/cmd/v1", "/pdb/cmd", "commands.service-time", "cmd.service-time"):
        cmd = next((b for b in service if hint in b), None)
        if cmd:
            break
    return query, cmd
