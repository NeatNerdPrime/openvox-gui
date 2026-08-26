"""Unit tests for fleet_scope (stub PuppetDB; no live estate)."""
from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, patch

from app.services import fleet_scope as m

FAKE_NODES = [
    {"certname": "ovcompiler1.pdxc-it.corp.int-x.ai"},
    {"certname": "ovcompiler1.atlc-it.corp.int-x.ai"},
    {"certname": "agent1.pdxc-it.corp.int-x.ai"},
    {"certname": "openvox.pdxc-it.corp.int-x.ai"},
]

FAKE_FACTS = [
    {"certname": "ovcompiler1.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
    {"certname": "ovcompiler1.atlc-it.corp.int-x.ai", "name": "location", "value": "ATLC"},
    {"certname": "agent1.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
    {"certname": "openvox.pdxc-it.corp.int-x.ai", "name": "location", "value": "PDXC"},
]


def _fake_pdb():
    pdb = AsyncMock()
    pdb.get_live_nodes = AsyncMock(return_value=FAKE_NODES)

    async def _query(endpoint, query=None, params=None):
        if endpoint == "facts":
            return FAKE_FACTS
        return []

    pdb._query = _query
    return pdb


def test_resolve_all():
    with patch.object(m, "puppetdb_service", _fake_pdb()):
        r = asyncio.run(m.resolve_scope("all"))
    assert r.total == 4
    assert r.kind == "all"


def test_resolve_location():
    with patch.object(m, "puppetdb_service", _fake_pdb()):
        r = asyncio.run(m.resolve_scope("location:ATLC"))
    assert r.total == 1
    assert "ovcompiler1.atlc-it.corp.int-x.ai" in r.certnames


def test_resolve_pack_compilers():
    with patch.object(m, "puppetdb_service", _fake_pdb()):
        r = asyncio.run(m.resolve_scope("pack:compilers"))
    assert r.total == 2
    assert all("ovcompiler" in c for c in r.certnames)


def test_resolve_pack_consoles():
    with patch.object(m, "puppetdb_service", _fake_pdb()):
        r = asyncio.run(m.resolve_scope("pack:consoles"))
    assert r.total == 1
    assert "openvox.pdxc-it.corp.int-x.ai" in r.certnames


def test_list_scopes_includes_locations():
    with patch.object(m, "puppetdb_service", _fake_pdb()):
        catalog = asyncio.run(m.list_scopes())
    ids = {s["id"] for s in catalog["scopes"]}
    assert "all" in ids
    assert "pack:compilers" in ids
    assert "location:ATLC" in ids
    assert "location:PDXC" in ids


def test_builtin_patterns_compile():
    for _pack_id, meta in m.BUILTIN_PACKS.items():
        re.compile(meta["pattern"], re.IGNORECASE)
