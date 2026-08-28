"""Clustered Agent Install one-liners must not point yum at the compiler VIP."""
from __future__ import annotations

from app.routers.installer import (
    _agent_install_commands,
    _noproxy_hosts,
    _pkg_repo_url,
)


def test_noproxy_lists_console_and_compiler_when_they_differ():
    assert (
        _noproxy_hosts("openvox.atlc-it.example.com", "ovcompilers.atlc-it.example.com")
        == "openvox.atlc-it.example.com,ovcompilers.atlc-it.example.com"
    )


def test_noproxy_dedupes_aio():
    assert _noproxy_hosts("openvox.example.com", "openvox.example.com") == "openvox.example.com"


def test_pkg_repo_url_is_console_not_compiler(monkeypatch):
    monkeypatch.setattr("app.routers.installer._local_fqdn", lambda: "openvox.atlc-it.example.com")
    monkeypatch.setattr("app.routers.installer._console_port", lambda: 4567)
    monkeypatch.delenv("OPENVOX_GUI_PKG_REPO_URL", raising=False)
    assert _pkg_repo_url() == "https://openvox.atlc-it.example.com:4567/packages"


def test_linux_command_passes_pkg_repo_url_and_server():
    linux, win = _agent_install_commands(
        "openvox.atlc-it.example.com",
        "ovcompilers.atlc-it.example.com",
        "https://openvox.atlc-it.example.com:4567/packages",
    )
    assert "--server ovcompilers.atlc-it.example.com" in linux
    assert (
        "--pkg-repo-url https://openvox.atlc-it.example.com:4567/packages"
        in linux
    )
    assert "ovcompilers.atlc-it.example.com:8140/packages" not in linux
    assert "-Server 'ovcompilers.atlc-it.example.com'" in win
    assert "-PkgRepoUrl 'https://openvox.atlc-it.example.com:4567/packages'" in win
    assert "--noproxy openvox.atlc-it.example.com,ovcompilers.atlc-it.example.com" in linux
