"""Clustered Hiera Lookup must not query the compiler's PuppetDB termini."""
from __future__ import annotations

from app.routers.config import PuppetLookupRequest, _lookup_clustered_shell


def test_lookup_shell_uses_facter_and_facts_flag():
    req = PuppetLookupRequest(key="message", node=None, environment="staging")
    shell = _lookup_clustered_shell(req)
    assert "facter --json" in shell
    assert "--facts" in shell
    assert "--node" not in shell
    assert "--environment staging" in shell
    assert "storeconfigs = false" in shell
    assert "facts_terminus = facter" in shell
    assert "--confdir" in shell


def test_lookup_shell_accepts_preloaded_facts():
    req = PuppetLookupRequest(key="os.family")
    shell = _lookup_clustered_shell(req, facts_b64="e30K")
    assert "base64 -d" in shell
    assert "facter --json" not in shell
    assert "--facts" in shell
