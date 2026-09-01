"""GUI Bolt runtime must not try to write .rerun.json (#63)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.routers import bolt_runtime


@pytest.mark.asyncio
async def test_run_bolt_command_passes_no_save_rerun():
    captured: dict = {}

    async def fake_sudo(args, timeout=120, env=None):
        captured["args"] = args
        return {"returncode": 0, "stdout": "", "stderr": ""}

    with (
        patch.object(bolt_runtime, "find_bolt", return_value="/opt/puppetlabs/bolt/bin/bolt"),
        patch.object(
            bolt_runtime,
            "sanitize_bolt_inventory",
            return_value="/etc/puppetlabs/bolt/inventory.yaml",
        ),
        patch.object(bolt_runtime, "run_sudo", new=fake_sudo),
    ):
        result = await bolt_runtime.run_bolt_command(
            ["command", "run", "true", "-t", "localhost"]
        )

    assert result["returncode"] == 0
    assert "--no-save-rerun" in captured["args"]
    assert captured["args"].count("--no-save-rerun") == 1
    assert "--project" in captured["args"]


@pytest.mark.asyncio
async def test_run_bolt_command_does_not_duplicate_no_save_rerun():
    captured: dict = {}

    async def fake_sudo(args, timeout=120, env=None):
        captured["args"] = args
        return {"returncode": 0, "stdout": "", "stderr": ""}

    with (
        patch.object(bolt_runtime, "find_bolt", return_value="/opt/puppetlabs/bolt/bin/bolt"),
        patch.object(
            bolt_runtime,
            "sanitize_bolt_inventory",
            return_value="/etc/puppetlabs/bolt/inventory.yaml",
        ),
        patch.object(bolt_runtime, "run_sudo", new=fake_sudo),
    ):
        await bolt_runtime.run_bolt_command(
            ["command", "run", "true", "-t", "localhost", "--no-save-rerun"]
        )

    assert captured["args"].count("--no-save-rerun") == 1


@pytest.mark.asyncio
async def test_run_bolt_command_tty_uses_pty_not_no_tty():
    captured: dict = {}

    async def fake_sudo(args, timeout=120, env=None):
        captured["args"] = args
        return {"returncode": 0, "stdout": "", "stderr": ""}

    with (
        patch.object(bolt_runtime, "find_bolt", return_value="/opt/puppetlabs/bolt/bin/bolt"),
        patch.object(
            bolt_runtime,
            "write_estate_bolt_inventory",
            return_value="/opt/openvox-gui/data/bolt-inventory.ca.yaml",
        ),
        patch.object(bolt_runtime, "run_sudo", new=fake_sudo),
    ):
        await bolt_runtime.run_bolt_command(
            ["command", "run", "true", "-t", "ovcompiler1.example.com", "--no-tty"],
            tty=True,
        )

    assert "--tty" in captured["args"]
    assert "--no-tty" not in captured["args"]
