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


_NOPROXY_PROFILE = Path("/etc/profile.d/noproxy.sh")


def _estate_no_proxy(env: Dict[str, str]) -> str:
    """Build no_proxy from profile.d (Puppet) plus process / GUI settings."""
    parts: list[str] = []

    def _add(blob: Optional[str]) -> None:
        if not blob:
            return
        for item in blob.split(","):
            host = item.strip().strip('"').strip("'")
            if host.startswith("export "):
                continue
            if "=" in host and host.split("=", 1)[0].lower() in ("no_proxy", "no_proxy"):
                host = host.split("=", 1)[-1].strip().strip('"').strip("'")
            if host and host not in parts:
                parts.append(host)

    if _NOPROXY_PROFILE.is_file():
        try:
            for line in _NOPROXY_PROFILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "no_proxy=" in line.lower():
                    _add(line.split("=", 1)[-1])
        except OSError:
            pass
    _add(env.get("NO_PROXY") or env.get("no_proxy"))
    try:
        from ..config import settings

        _add(getattr(settings, "no_proxy", None))
    except Exception:
        pass
    return ",".join(parts)


def find_bolt() -> Optional[str]:
    for p in BOLT_PATHS:
        if Path(p).exists():
            return p
    return shutil.which("bolt")


def _clean_inventory_data(data: Any) -> Any:
    """Drop keys OpenBolt 5 rejects; drop ENC plugin until its task is patched."""
    if not isinstance(data, dict):
        return data
    cfg = data.get("config")
    if isinstance(cfg, dict):
        cfg.pop("puppetdb", None)
        data["config"] = {
            k: v for k, v in cfg.items() if k in ("transport", "ssh", "winrm", "docker", "local", "pcp")
        }
    cleaned = []
    for group in data.get("groups") or []:
        if not isinstance(group, dict):
            continue
        group.pop("description", None)
        targets = group.get("targets") or []
        uses_enc = any(
            isinstance(t, dict) and t.get("_plugin") == "openvox_enc" for t in targets
        )
        if uses_enc:
            continue
        cleaned.append(group)
    data["groups"] = cleaned
    return data


def sanitize_bolt_inventory(
    src: str = "/etc/puppetlabs/bolt/inventory.yaml",
    dest: str = "/opt/openvox-gui/data/bolt-inventory.sanitized.yaml",
) -> str:
    """Write a console-safe inventory the GUI user can always write.

    /etc/puppetlabs/bolt/inventory.yaml is 640 root:bolt; sanitize used to
    fail silently and Bolt kept the dirty file. Always emit a cleaned copy
    under the GUI data dir and return that path for ``-i``.
    """
    try:
        import yaml
    except ImportError:
        return src
    raw = Path(src)
    if not raw.is_file():
        return src
    try:
        data = yaml.safe_load(raw.read_text(encoding="utf-8"))
    except Exception:
        return src
    data = _clean_inventory_data(data)
    out = Path(dest)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return str(out)
    except OSError:
        return src


async def run_bolt_command(args: List[str], timeout: int = 120) -> Dict[str, Any]:
    bolt = find_bolt()
    if not bolt:
        return {"returncode": -1, "stdout": "", "stderr": "OpenBolt is not installed"}

    inv_path = "/etc/puppetlabs/bolt/inventory.yaml"
    try:
        inv_path = sanitize_bolt_inventory()
    except Exception:
        pass

    inventory_flag = ["-i", inv_path]
    project_flag = ["--project", "/etc/puppetlabs/bolt"]

    is_rainbow = "--format" in args and "rainbow" in args
    if is_rainbow and "--color" not in args:
        args = list(args) + ["--color"]

    bolt_args = ["sudo", "-E", "-u", "bolt", bolt] + args + inventory_flag + project_flag

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    # Same bypass list as /etc/profile.d/noproxy.sh (profiles::base::nixenv).
    # sudo -u bolt is non-login, so we inject it here. Leave http(s)_proxy set.
    bypass = _estate_no_proxy(env)
    env["NO_PROXY"] = bypass
    env["no_proxy"] = bypass
    result = await run_sudo(bolt_args, timeout=timeout, env=env)
    if is_rainbow and isinstance(result.get("stdout"), str):
        out = result["stdout"].replace("\r\n", "\n").replace("\r", "")
        result = {**result, "stdout": out}
    return result
