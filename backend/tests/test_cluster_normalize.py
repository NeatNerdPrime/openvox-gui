"""Cluster config FQDN / normalize helpers (no live topology required)."""
from __future__ import annotations

import pytest

from app.services.cluster_config import DEFAULT_CONFIG, _normalize, _validate_fqdn


def test_validate_fqdn_accepts_normal_hosts():
    assert _validate_fqdn("ovcompiler1.example.com") == "ovcompiler1.example.com"
    assert _validate_fqdn("OpenVox.Example.COM") == "openvox.example.com"


def test_validate_fqdn_rejects_junk():
    with pytest.raises(ValueError):
        _validate_fqdn("")
    with pytest.raises(ValueError):
        _validate_fqdn("no-dots")
    with pytest.raises(ValueError):
        _validate_fqdn("bad host.example.com")
    with pytest.raises(ValueError):
        _validate_fqdn("-leading.example.com")


def test_normalize_defaults_and_mode_fallback():
    out = _normalize({})
    assert out["deployment_mode"] == "single"
    assert out["database_backend"] == "sqlite"
    assert out["compilers"] == []
    assert set(DEFAULT_CONFIG).issubset(out)


def test_normalize_rejects_unknown_mode_and_backend():
    out = _normalize({"deployment_mode": "magic", "database_backend": "oracle"})
    assert out["deployment_mode"] == "single"
    assert out["database_backend"] == "sqlite"


def test_normalize_lowercases_member_lists():
    out = _normalize(
        {
            "deployment_mode": "clustered",
            "compilers": ["OVCompiler1.Example.COM"],
            "consoles": ["OpenVox.Example.COM"],
        }
    )
    assert out["deployment_mode"] == "clustered"
    assert out["compilers"] == ["ovcompiler1.example.com"]
    assert out["consoles"] == ["openvox.example.com"]
