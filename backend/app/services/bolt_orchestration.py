"""
Bolt orchestration domain logic extracted from routers/bolt.py (srdev2 A1/A4).

Keeps the FastAPI router thinner: command normalization, privilege heuristics,
execution-history bookends. Actual Bolt CLI argv assembly stays in routers.bolt
(run_bolt_command) for lab-proven behavior.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ExecutionHistory
from ..utils.validation import strip_ansi

logger = logging.getLogger(__name__)

# Puppet agent -t wait for daemon/cron run lock (seconds). Avoids exit 1
# "agent_catalog_run.lock exists" when the agent service is mid-run.
PUPPET_AGENT_WAITFORLOCK_SECS = 300

# Puppet agent exit codes treated as success for GUI/Bolt result interpretation:
# 0 = no changes, 2 = changes applied (still a successful run).
PUPPET_AGENT_SUCCESS_EXIT_CODES = frozenset({0, 2})

_LOCK_NOTICE_RE = re.compile(
    r"already in progress|agent_catalog_run\.lock",
    re.IGNORECASE,
)
# Bolt human format noise (inventory tty vs --no-tty, progress spinner glyphs)
_CLI_OVERRIDES_RE = re.compile(
    r"CLI arguments\s+\[.*?\]\s+might be overridden by Inventory:[^\n]*\n?",
    re.IGNORECASE,
)
_BOLT_SPINNER_RE = re.compile(r"(?:\\\|/\\-)+")
_HUMAN_EXIT_RE = re.compile(
    r"The command failed with exit code\s+(\d+)",
    re.IGNORECASE,
)
_HUMAN_FAILED_ON_RE = re.compile(
    r"Failed on\s+(\S+):\s*The command failed with exit code\s+(\d+)",
    re.IGNORECASE,
)


def clean_bolt_console_text(text: str) -> str:
    """Strip NULs, inventory override banners, and spinner junk from Bolt human output."""
    if not text:
        return ""
    t = text.replace("\x00", "")
    t = _CLI_OVERRIDES_RE.sub("", t)
    t = _BOLT_SPINNER_RE.sub("", t)
    # Collapse runs of blank lines
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


class BoltRunResultModel(BaseModel):
    """Stable API contract for POST /api/bolt/run/* (srdev2 A3)."""

    returncode: int
    output: str = ""
    error: str = ""


def _is_puppet_agent_invocation(command: str) -> bool:
    cl = (command or "").lower()
    return "puppet agent" in cl or "puppet-agent" in cl


def normalize_command_for_gui(command: str) -> str:
    """
    Make common commands more reliable when invoked from the GUI.

    For Puppet agent: full binary path (sudo ``secure_path`` has no
    ``/opt/puppetlabs/bin``), ``--config`` so *this host's* puppet.conf
    wins (CA nodes use ``ssldir=/mnt/openvox-ca/ssl``), and
    ``--waitforlock``. Do **not** hard-code ``--ssldir`` /
    ``PUPPET_SSLDIR`` to ``/etc/puppetlabs/puppet/ssl`` — that leftover
    tree on ovca* is not the live DRBD CA ssldir and makes the agent
    mint a new key.
    """
    cmd = command.strip()
    if not cmd:
        return cmd

    is_puppet_command = False
    if cmd.startswith("puppet ") or cmd == "puppet":
        cmd = cmd.replace("puppet", "/opt/puppetlabs/bin/puppet", 1)
        is_puppet_command = True
    elif cmd.startswith("puppet-agent ") or cmd == "puppet-agent":
        cmd = cmd.replace("puppet-agent", "/opt/puppetlabs/bin/puppet", 1)
        is_puppet_command = True

    cmd_lower = cmd.lower()
    if "puppet agent" in cmd_lower or "puppet-agent" in cmd_lower:
        is_puppet_command = True

    if is_puppet_command:
        if not cmd.startswith("env "):
            cmd = "env PUPPET_CONFDIR=/etc/puppetlabs/puppet " + cmd
        if "puppet agent" in cmd or "puppet-agent" in cmd:
            if "--config" not in cmd:
                cmd += " --config /etc/puppetlabs/puppet/puppet.conf"
            if "--waitforlock" not in cmd.lower() and "agent_catalog_run.lock" not in cmd:
                cmd += f" --waitforlock {PUPPET_AGENT_WAITFORLOCK_SECS}"

    return cmd


def _iter_bolt_result_items(stdout: str) -> List[Dict[str, Any]]:
    """Parse Bolt --format json items list from stdout when present."""
    text = (stdout or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Sometimes bolt wraps or prefixes; try to find first { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [i for i in data["items"] if isinstance(i, dict)]
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    return []


def _target_exit_code(item: Dict[str, Any]) -> Optional[int]:
    val = item.get("value")
    if isinstance(val, dict) and "exit_code" in val:
        try:
            return int(val["exit_code"])
        except (TypeError, ValueError):
            return None
    return None


def _target_merged_text(item: Dict[str, Any]) -> str:
    val = item.get("value")
    if not isinstance(val, dict):
        return ""
    parts = [
        str(val.get("stdout") or ""),
        str(val.get("stderr") or ""),
        str(val.get("merged_output") or ""),
    ]
    err = val.get("_error")
    if isinstance(err, dict):
        parts.append(str(err.get("msg") or ""))
    return "\n".join(parts)


def reinterpret_puppet_agent_bolt_result(
    result: Dict[str, Any],
    *,
    original_command: str,
) -> Dict[str, Any]:
    """
    Adjust Bolt result for GUI semantics on ``puppet agent`` runs.

    - Puppet exit **2** (changes applied) is success; Bolt often surfaces it as failure
      with human text ``Failed on … exit code 2``.
    - Prefer per-target exit codes from ``--format json`` when available.
    - Strip inventory tty / spinner noise from console text.
    - Annotate lock-related failures so operators know it is not SSH/sudo failure.
    """
    out = dict(result)
    out["stdout"] = clean_bolt_console_text(out.get("stdout") or "")
    out["stderr"] = clean_bolt_console_text(out.get("stderr") or "")

    if not _is_puppet_agent_invocation(original_command):
        return out

    stdout = out.get("stdout") or ""
    items = _iter_bolt_result_items(stdout)
    notes: List[str] = []

    if items:
        exits = [_target_exit_code(i) for i in items]
        known = [e for e in exits if e is not None]
        all_ok = bool(known) and all(e in PUPPET_AGENT_SUCCESS_EXIT_CODES for e in known)
        failed = [
            (i.get("target") or "?", _target_exit_code(i))
            for i in items
            if _target_exit_code(i) not in PUPPET_AGENT_SUCCESS_EXIT_CODES
            and _target_exit_code(i) is not None
        ]

        if all_ok:
            # e.g. mix of 0 and 2 — treat as success; preserve worst "interesting" code 2 if any
            out["returncode"] = 2 if 2 in known else 0
            if 2 in known:
                notes.append(
                    "Note: Puppet exit code 2 means changes were applied (success). "
                    "GUI treats 0 and 2 as successful agent runs."
                )
        elif failed:
            lock_targets = [
                i.get("target") or "?"
                for i in items
                if _LOCK_NOTICE_RE.search(_target_merged_text(i) or "")
            ]
            if lock_targets and len(lock_targets) == len(failed):
                notes.append(
                    "One or more targets reported agent_catalog_run.lock / run already in progress. "
                    "Another agent run (daemon, cron, or concurrent GUI click) held the lock. "
                    "GUI now passes --waitforlock; retry or wait for the lock on: "
                    + ", ".join(str(t) for t in lock_targets)
                )
            elif lock_targets:
                notes.append(
                    "Partial fleet run: lock contention on "
                    + ", ".join(str(t) for t in lock_targets)
                    + ". Other targets may have succeeded (check JSON items)."
                )
            # Keep Bolt returncode (non-zero) but surface guidance in stderr for the UI error pane
            hint = "\n".join(notes)
            prev_err = out.get("stderr") or ""
            out["stderr"] = (prev_err + "\n" + hint).strip() if hint else prev_err
            return out
    else:
        # Human/plain output — Bolt prints "Failed on … exit code 2" even when Puppet succeeded
        rc = out.get("returncode")
        try:
            rc_i = int(rc) if rc is not None else -1
        except (TypeError, ValueError):
            rc_i = -1
        text = f"{stdout}\n{out.get('stderr') or ''}"

        # Prefer explicit "exit code N" in Bolt human banner over process rc
        human_exits = [int(m.group(2)) for m in _HUMAN_FAILED_ON_RE.finditer(text)]
        if not human_exits:
            human_exits = [int(m.group(1)) for m in _HUMAN_EXIT_RE.finditer(text)]
        if human_exits and all(e in PUPPET_AGENT_SUCCESS_EXIT_CODES for e in human_exits):
            rc_i = 2 if 2 in human_exits else 0
            out["returncode"] = rc_i
            # Rewrite misleading Failed banners
            cleaned = stdout
            cleaned = _HUMAN_FAILED_ON_RE.sub(
                lambda m: (
                    f"Succeeded on {m.group(1)}: puppet agent finished with exit code {m.group(2)}"
                    + (
                        " (changes applied)"
                        if m.group(2) == "2"
                        else " (no changes)"
                    )
                ),
                cleaned,
            )
            out["stdout"] = cleaned
            stdout = cleaned
            if rc_i == 2:
                notes.append(
                    "Note: Puppet exit code 2 means changes were applied (success). "
                    "Bolt human format labels that as Failed; the GUI treats 0 and 2 as success."
                )
            else:
                notes.append("Note: Puppet agent completed successfully (exit 0).")
        elif rc_i == 2:
            out["returncode"] = 2
            notes.append(
                "Note: Puppet exit code 2 means changes were applied (success)."
            )
            # Still rewrite Failed-on lines if present with code 2
            if _HUMAN_FAILED_ON_RE.search(stdout):
                out["stdout"] = _HUMAN_FAILED_ON_RE.sub(
                    lambda m: (
                        f"Succeeded on {m.group(1)}: puppet agent finished with exit code {m.group(2)}"
                        + (" (changes applied)" if m.group(2) == "2" else "")
                    ),
                    stdout,
                )
                stdout = out["stdout"]
        elif rc_i == 1 and _LOCK_NOTICE_RE.search(text):
            notes.append(
                "Agent run skipped: catalog run lock exists (another run in progress). "
                "Retry after the daemon finishes, or use --waitforlock (added automatically for GUI runs)."
            )

    if notes and items and all(
        _target_exit_code(i) in PUPPET_AGENT_SUCCESS_EXIT_CODES
        for i in items
        if _target_exit_code(i) is not None
    ):
        hint = "\n".join(notes)
        # Append success notes to stdout so PrettyJson / OutputPane still shows main payload first
        out["stdout"] = (stdout.rstrip() + "\n\n" + hint).strip() if hint else stdout

    if notes and not items:
        hint = "\n".join(notes)
        prev_err = out.get("stderr") or ""
        if "exit code 2" in hint.lower() or "changes were applied" in hint.lower() or "completed successfully" in hint.lower():
            out["stdout"] = ((stdout or "") + "\n\n" + hint).strip()
        else:
            out["stderr"] = (prev_err + "\n" + hint).strip() if hint else prev_err

    return out


def puppet_agent_run_succeeded(result: Dict[str, Any], original_command: str) -> bool:
    """True if GUI should treat the bolt result as a successful puppet agent run."""
    if not _is_puppet_agent_invocation(original_command):
        return result.get("returncode") == 0
    try:
        rc = int(result.get("returncode") if result.get("returncode") is not None else -1)
    except (TypeError, ValueError):
        return False
    if rc in PUPPET_AGENT_SUCCESS_EXIT_CODES:
        return True
    items = _iter_bolt_result_items(result.get("stdout") or "")
    if not items:
        return False
    exits = [_target_exit_code(i) for i in items]
    known = [e for e in exits if e is not None]
    return bool(known) and all(e in PUPPET_AGENT_SUCCESS_EXIT_CODES for e in known)


def command_needs_root(command: str) -> bool:
    """Heuristic: GUI command typically needs root on the target (legacy bolt router)."""
    cmd_lower = command.lower().strip()
    privileged_patterns = [
        "puppet agent",
        "puppet apply",
        "systemctl restart",
        "systemctl stop",
        "systemctl start",
        "service ",
        "yum ",
        "dnf ",
        "apt-get ",
        "apt ",
        "rpm ",
        "dpkg ",
        "mount ",
        "umount ",
        "reboot",
        "shutdown",
        "init ",
    ]
    for pattern in privileged_patterns:
        if cmd_lower.startswith(pattern) or f" {pattern}" in cmd_lower:
            return True
    return False


def apply_escalation(normalized_command: str, run_as: Optional[str]) -> tuple[str, bool]:
    """
    Return (command_to_run, escalate_flag).

    Root path uses a ``sudo `` prefix so the bolt OS user exercises target sudoers.
    """
    escalate = bool(run_as) or command_needs_root(normalized_command)
    command = ("sudo " + normalized_command) if escalate else normalized_command
    return command, escalate


async def start_execution_history(
    db: AsyncSession,
    *,
    execution_type: str,
    node_name: str,
    executed_by: str,
    command_name: Optional[str] = None,
    task_name: Optional[str] = None,
    plan_name: Optional[str] = None,
    result_format: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Optional[ExecutionHistory]:
    """Insert running ExecutionHistory row and commit.

    Best-effort: a missing table or locked SQLite must not 500 the Run button.
    """
    try:
        history_entry = ExecutionHistory(
            execution_type=execution_type,
            node_name=node_name,
            command_name=command_name,
            task_name=task_name,
            plan_name=plan_name,
            result_format=result_format,
            status="running",
            executed_by=executed_by,
            parameters=parameters,
        )
        db.add(history_entry)
        await db.commit()
        await db.refresh(history_entry)
        return history_entry
    except Exception as e:
        logger.warning("execution_history start failed: %s", e, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


async def finish_execution_history(
    db: AsyncSession,
    history_entry: Optional[ExecutionHistory],
    result: Dict[str, Any],
    start_time: float,
    *,
    original_command: Optional[str] = None,
) -> None:
    """Update history from bolt result dict (returncode/stdout/stderr)."""
    if history_entry is None:
        return
    duration_ms = int((time.time() - start_time) * 1000)
    ok = (
        puppet_agent_run_succeeded(result, original_command)
        if original_command
        else result.get("returncode") == 0
    )
    # Also accept exit 2 without command context (generic bolt success-with-changes)
    if not ok:
        try:
            if int(result.get("returncode") if result.get("returncode") is not None else -1) == 2:
                ok = True
        except (TypeError, ValueError):
            pass
    history_entry.status = "success" if ok else "failure"
    history_entry.duration_ms = duration_ms
    stderr = result.get("stderr") or ""
    stdout = result.get("stdout") or ""
    if not ok:
        history_entry.error_message = stderr[:500] if stderr else None
    history_entry.result_preview = stdout[:500] if stdout else None
    try:
        await db.commit()
    except Exception as e:
        logger.warning("execution_history finish failed: %s", e, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass


def summarize_bolt_item_failures(stdout: str) -> str:
    """Pull target stderr / _error.msg out of Bolt --format json."""
    bits: List[str] = []
    for item in _iter_bolt_result_items(stdout or ""):
        if (item.get("status") or "").lower() == "success":
            continue
        val = item.get("value") if isinstance(item.get("value"), dict) else {}
        err = ""
        if isinstance(val.get("_error"), dict):
            err = str(val["_error"].get("msg") or "")
        err = (err + "\n" + str(val.get("stderr") or "") + "\n" + str(val.get("stdout") or "")).strip()
        if not err:
            err = _target_merged_text(item).strip() or "no stderr"
        bits.append(
            f"{item.get('target') or '?'}: exit {val.get('exit_code', '?')}: {err}"
        )
    return "\n".join(bits)


def sanitize_bolt_result(result: Dict[str, Any]) -> BoltRunResultModel:
    """Map run_bolt_command dict → API model with ANSI / Bolt noise stripped."""
    stdout = strip_ansi(clean_bolt_console_text(result.get("stdout") or ""))
    stderr = strip_ansi(clean_bolt_console_text(result.get("stderr") or ""))
    item_err = summarize_bolt_item_failures(result.get("stdout") or "")
    if item_err:
        stderr = (item_err + ("\n" + stderr if stderr else "")).strip()
    return BoltRunResultModel(
        returncode=int(result.get("returncode") if result.get("returncode") is not None else -1),
        output=stdout,
        error=stderr,
    )
