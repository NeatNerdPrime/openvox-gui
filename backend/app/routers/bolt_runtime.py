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


# Must exist on every target before `bolt script run`. OpenBolt uses
# `mkdir -m 700 $tmpdir/<uuid>` (no -p). CIS /tmp is noexec so this cannot
# be /tmp. Stage/Activate pre-creates this path as root.
BOLT_REMOTE_TMPDIR = "/home/bolt/.bolt/tmp"

_SSH_CONFIG_BLOCK = """config:
  transport: ssh
  ssh:
    user: bolt
    private-key: /etc/puppetlabs/bolt/id_bolt
    host-key-check: false
    tty: {tty}
    connect-timeout: 10
    tmpdir: """ + BOLT_REMOTE_TMPDIR + """
"""


def _estate_target_uris() -> List[str]:
    """FQDNs Bolt may need for infra health / logs / HA — from cluster config, not PDB."""
    hosts: list[str] = []
    try:
        from ..services.estate_inventory import discover_serving_estate

        est = discover_serving_estate()
        for t in est.get("all_probe_targets") or []:
            fq = (t.get("fqdn") or "").strip().lower()
            if fq and fq not in hosts:
                hosts.append(fq)
        for key in (
            "compilers",
            "compiler_vips",
            "puppetdb_nodes",
            "puppetdb_vips",
            "ca_nodes",
            "ca_vips",
            "consoles",
            "console_vips",
        ):
            for h in est.get(key) or []:
                fq = str(h).strip().lower()
                if fq and fq not in hosts:
                    hosts.append(fq)
    except Exception:
        pass
    return hosts


def _make_path_traversable_for_others(path: Path) -> None:
    """Ensure bolt (other user) can traverse parents under /opt/openvox-gui."""
    for parent in [path.parent, *list(path.parents)[:6]]:
        try:
            p = str(parent)
            if p in ("/", ""):
                break
            if not p.startswith("/opt/openvox-gui"):
                continue
            st = parent.stat()
            # o+x on dirs so user bolt can walk to the file
            os.chmod(parent, st.st_mode | 0o0111 | 0o0005)
        except OSError:
            continue


def _make_bolt_readable(path: Path) -> None:
    """File must be readable by ``sudo -u bolt`` (often not in puppet group)."""
    try:
        # world-readable inventory (no secrets — only hostnames + ssh key *path*)
        os.chmod(path, 0o644)
    except OSError:
        try:
            path.chmod(0o644)
        except OSError:
            pass
    _make_path_traversable_for_others(path)
    # Best-effort: also publish under bolt's project dir (root may own it)
    alt = Path("/etc/puppetlabs/bolt/openvox-gui-estate.yaml")
    try:
        if path.is_file() and path.resolve() != alt.resolve():
            import shutil

            # Prefer copy as current user; if denied, leave primary path only
            try:
                shutil.copy2(path, alt)
                os.chmod(alt, 0o644)
            except OSError:
                pass
    except Exception:
        pass


def write_estate_bolt_inventory(
    dest: str = "/opt/openvox-gui/data/bolt-inventory.estate.yaml",
    *,
    tty: bool = False,
) -> str:
    """Bolt inventory for dedicated consoles: SSH defaults + explicit estate FQDNs.

    Does **not** use PuppetDB inventory plugin. File + parent dirs are made
    readable by user ``bolt`` (was 0640 under puppet:puppet → unreadable).
    ``tty=True`` is for CA mutate (sudo requiretty on ovca*).
    """
    ssh_block = _SSH_CONFIG_BLOCK.format(tty="true" if tty else "false")
    lines = [
        "---",
        "# Generated by openvox-gui for infra/logs/HA probes.",
        "# Targets = cluster_config + OPENVOX_GUI_* hosts (not PuppetDB inventory).",
        "# Must be readable by system user bolt (chmod 644).",
        ssh_block.rstrip(),
        "targets:",
    ]
    uris = _estate_target_uris()
    if not uris:
        lines.append("  - uri: localhost")
        lines.append("    config:")
        lines.append("      transport: local")
    else:
        for h in uris:
            lines.append(f"  - uri: {h}")
            lines.append(f"    name: {h}")
    lines.extend(
        [
            "groups:",
            "  - name: enc",
            "    targets:",
            "      _plugin: openvox_enc",
            "      api_url: 'https://127.0.0.1:4567'",
            "      token_file: /etc/puppetlabs/bolt/.bolt_token",
            "",
        ]
    )
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    _make_bolt_readable(out)

    # Prefer a path under the bolt project if we successfully copied it
    alt = Path("/etc/puppetlabs/bolt/openvox-gui-estate.yaml")
    if alt.is_file():
        try:
            if os.access(alt, os.R_OK):
                # Verify bolt user can read (best-effort)
                return str(alt)
        except OSError:
            pass
    return str(out)


def sanitize_bolt_inventory(
    src: str = "/etc/puppetlabs/bolt/inventory.yaml",
    dest: str = "/opt/openvox-gui/data/bolt-inventory.sanitized.yaml",
) -> str:
    """Hand Bolt a bolt-readable inventory (estate FQDNs + SSH). Never require /etc root file."""
    del src
    try:
        return write_estate_bolt_inventory(
            dest="/opt/openvox-gui/data/bolt-inventory.estate.yaml"
        )
    except OSError:
        out = Path(dest)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                "---\n"
                + _SSH_CONFIG_BLOCK.format(tty="false")
                + "targets:\n  - uri: localhost\n    config:\n      transport: local\n",
                encoding="utf-8",
            )
            _make_bolt_readable(out)
            return str(out)
        except OSError:
            return dest


async def run_bolt_command(
    args: List[str],
    timeout: int = 120,
    *,
    tty: bool = False,
) -> Dict[str, Any]:
    bolt = find_bolt()
    if not bolt:
        return {"returncode": -1, "stdout": "", "stderr": "OpenBolt is not installed"}

    inv_path = "/etc/puppetlabs/bolt/inventory.yaml"
    try:
        if tty:
            inv_path = write_estate_bolt_inventory(
                dest="/opt/openvox-gui/data/bolt-inventory.ca.yaml",
                tty=True,
            )
        else:
            inv_path = sanitize_bolt_inventory()
    except Exception:
        pass

    inventory_flag = ["-i", inv_path]
    project_flag = ["--project", "/etc/puppetlabs/bolt"]

    is_rainbow = "--format" in args and "rainbow" in args
    if is_rainbow and "--color" not in args:
        args = list(args) + ["--color"]
    # Human/json: no TTY so Bolt does not emit CR spinner frames (\\|/- noise).
    # CA mutate needs a PTY — ovca sudoers often has requiretty.
    if tty:
        args = [a for a in args if a != "--no-tty"]
        if "--tty" not in args:
            args = list(args) + ["--tty"]
    elif not is_rainbow and "--no-tty" not in args:
        args = list(args) + ["--no-tty"]

    # Dedicated consoles leave /etc/puppetlabs/bolt as root:bolt 0750.
    # Bolt then cannot write .rerun.json; the GUI does not use rerun.
    # Reported by @miharp (#63).
    if "--no-save-rerun" not in args:
        args = list(args) + ["--no-save-rerun"]

    bolt_args = ["sudo", "-E", "-u", "bolt", bolt] + args + inventory_flag + project_flag

    env = os.environ.copy()
    env["TERM"] = "xterm-256color" if is_rainbow else "dumb"
    # Same bypass list as /etc/profile.d/noproxy.sh (profiles::base::nixenv).
    # sudo -u bolt is non-login, so we inject it here. Leave http(s)_proxy set.
    bypass = _estate_no_proxy(env)
    env["NO_PROXY"] = bypass
    env["no_proxy"] = bypass
    result = await run_sudo(bolt_args, timeout=timeout, env=env)
    from ..utils.validation import strip_ansi

    if isinstance(result.get("stdout"), str):
        result = {**result, "stdout": strip_ansi(result["stdout"])}
    if isinstance(result.get("stderr"), str):
        result = {**result, "stderr": strip_ansi(result["stderr"])}
    return result
