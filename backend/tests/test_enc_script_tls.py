"""scripts/enc.py TLS context: verify on for FQDNs, off only when asked."""
from __future__ import annotations

import importlib.util
import ssl
from pathlib import Path


def _load_enc():
    path = Path(__file__).resolve().parents[2] / "scripts" / "enc.py"
    spec = importlib.util.spec_from_file_location("openvox_enc_script", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_ssl_context_verify_off(monkeypatch):
    enc = _load_enc()
    monkeypatch.setenv("OPENVOX_GUI_ENC_TLS_VERIFY", "0")
    ctx = enc._ssl_context("https://openvox.corp.int-x.ai:4567")
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
