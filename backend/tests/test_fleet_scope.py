"""Unit tests for fleet_scope (no FastAPI / PuppetDB required)."""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path


def _install_stubs():
    if "app.services.puppetdb" in sys.modules:
        return
    pkg = types.ModuleType("app")
    pkg.__path__ = []
    sys.modules["app"] = pkg
    svc = types.ModuleType("app.services")
    svc.__path__ = []
    sys.modules["app.services"] = svc
    pdb = types.ModuleType("app.services.puppetdb")

    class FakePDB:
        async def get_live_nodes(self):
            return [
                {"certname": "ovcompiler1.pdxc-it.corp.int-x.ai"},
                {"certname": "ovcompiler1.atlc-it.corp.int-x.ai"},
                {"certname": "agent1.pdxc-it.corp.int-x.ai"},
                {"certname": "openvox.pdxc-it.corp.int-x.ai"},
            ]

        async def _query(self, endpoint, query=None, params=None):
            if endpoint == "facts":
                return [
                    {"certname": "ovcompiler1.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
                    {"certname": "ovcompiler1.atlc-it.corp.int-x.ai", "name": "location", "value": "ATLC"},
                    {"certname": "agent1.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
                    {"certname": "openvox.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
                ]
            return []

    pdb.puppetdb_service = FakePDB()
    sys.modules["app.services.puppetdb"] = pdb


def _load():
    _install_stubs()
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "app" / "services" / "fleet_scope.py"
    spec = importlib.util.spec_from_file_location("app.services.fleet_scope", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.services.fleet_scope"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_resolve_all():
    import asyncio

    m = _load()
    r = asyncio.run(m.resolve_scope("all"))
    assert r.total == 4
    assert r.kind == "all"


def test_resolve_location():
    import asyncio

    m = _load()
    r = asyncio.run(m.resolve_scope("location:ATLC"))
    assert r.total == 1
    assert "ovcompiler1.atlc-it.corp.int-x.ai" in r.certnames


def test_resolve_pack_compilers():
    import asyncio

    m = _load()
    r = asyncio.run(m.resolve_scope("pack:compilers"))
    assert r.total == 2
    assert all("ovcompiler" in c for c in r.certnames)


def test_resolve_pack_consoles():
    import asyncio

    m = _load()
    r = asyncio.run(m.resolve_scope("pack:consoles"))
    assert r.total == 1
    assert "openvox.pdxc-it.corp.int-x.ai" in r.certnames


def test_list_scopes_includes_locations():
    import asyncio

    m = _load()
    catalog = asyncio.run(m.list_scopes())
    ids = {s["id"] for s in catalog["scopes"]}
    assert "all" in ids
    assert "pack:compilers" in ids
    assert "location:ATLC" in ids
    assert "location:PDXC" in ids


def test_builtin_patterns_compile():
    m = _load()
    for pack_id, meta in m.BUILTIN_PACKS.items():
        re.compile(meta["pattern"], re.IGNORECASE)
