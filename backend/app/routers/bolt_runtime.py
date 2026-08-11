"""Shared Bolt CLI runtime (find binary, run argv, resolve targets). srdev2 split."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..services.execution import resolve_targets as execution_resolve_targets
from ..utils.sudo import run_sudo

BOLT_PATHS = [
    "/opt/puppetlabs/bolt/bin/bolt",
    "/opt/puppetlabs/bin/bolt",
    "/usr/local/bin/bolt",
]


async def resolve_targets(targets: str, db: AsyncSession) -> str:
    return await execution_resolve_targets(targets, db)


def find_bolt() -> Optional[str]:
    for p in BOLT_PATHS:
        if Path(p).exists():
            return p
    return shutil.which("bolt")


def sanitize_bolt_inventory(path: str = "/etc/puppetlabs/bolt/inventory.yaml") -> None:
    """Strip keys OpenBolt rejects (legacy ENC sync / enable script)."""
    inv = Path(path)
    if not inv.is_file():
        return
    try:
        import yaml
    except ImportError:
        return
    try:
        data = yaml.safe_load(inv.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    changed = False
    cfg = data.get("config")
    if isinstance(cfg, dict) and "puppetdb" in cfg:
        cfg.pop("puppetdb", None)
        changed = True
    groups = data.get("groups")
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict) and "description" in group:
                group.pop("description", None)
                changed = True
    if changed:
        inv.write_text(
            yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )


async def run_bolt_command(args: List[str], timeout: int = 120) -> Dict[str, Any]:


async def run_bolt_command(args: List[str], timeout: int = 120) -> Dict[str, Any]:
    bolt = find_bolt()
    if not bolt:
        return {"returncode": -1, "stdout": "", "stderr": "OpenBolt is not installed"}

    try:
        sanitize_bolt_inventory()
    except Exception:
        pass

    inventory_flag = ["-i", "/etc/puppetlabs/bolt/inventory.yaml"]
    project_flag = ["--project", "/etc/puppetlabs/bolt"]

    is_rainbow = "--format" in args and "rainbow" in args
    if is_rainbow and "--color" not in args:
        args = list(args) + ["--color"]

    bolt_args = ["sudo", "-E", "-u", "bolt", bolt] + args + inventory_flag + project_flag

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    # OpenVoxDB / CA / ENC are on-net. Corp Squid returns 407 for them.
    for key in list(env):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy"):
            del env[key]
    bypass = (
        "localhost,127.0.0.1,::1,"
        "ovdb.corp.int-x.ai,ovca.corp.int-x.ai,"
        "ovcompilers.pdxc-it.corp.int-x.ai,ovcompilers.atlc-it.corp.int-x.ai"
    )
    env["NO_PROXY"] = bypass
    env["no_proxy"] = bypass
    result = await run_sudo(bolt_args, timeout=timeout, env=env)
    if is_rainbow and isinstance(result.get("stdout"), str):
        out = result["stdout"].replace("\r\n", "\n").replace("\r", "")
        result = {**result, "stdout": out}
    return result
