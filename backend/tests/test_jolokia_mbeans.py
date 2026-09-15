"""Jolokia ObjectName escaping and HTTP/storage bean selection."""
from __future__ import annotations

from app.utils.jolokia import (
    escape_jolokia_path,
    jolokia_row_value,
    normalize_mbean,
    pick_http_latency_beans,
    timer_present,
    unescape_jolokia_mbean,
)


def test_unescape_and_normalize_match_escaped_and_plain():
    escaped = "puppetlabs.puppetdb.http:name=!/pdb!/query/v4.service-time"
    plain = "puppetlabs.puppetdb.http:name=/pdb/query/v4.service-time"
    assert unescape_jolokia_mbean(escaped) == plain
    assert normalize_mbean(escaped) == normalize_mbean(plain)


def test_escape_does_not_double_bang():
    plain = "puppetlabs.puppetdb.http:name=/pdb/cmd/v1.service-time"
    once = escape_jolokia_path(plain)
    assert once == "puppetlabs.puppetdb.http:name=!/pdb!/cmd!/v1.service-time"
    assert escape_jolokia_path(once) == once


def test_jolokia_row_value_drops_errors():
    assert jolokia_row_value({"status": 200, "value": {"Mean": 12}}) == {"Mean": 12}
    assert jolokia_row_value({"status": 404, "error": "InstanceNotFoundException"}) is None
    assert jolokia_row_value({"error_type": "x", "error": "nope", "status": 404}) is None


def test_timer_present():
    assert timer_present({"Mean": 1.5}) is True
    assert timer_present({"error": "missing"}) is False
    assert timer_present(None) is False
    assert timer_present(0.4) is True


def test_pick_http_latency_prefers_versioned_urls():
    beans = [
        "puppetlabs.puppetdb.http:name=/pdb/query/v4.service-time",
        "puppetlabs.puppetdb.http:name=/pdb/query/v4/nodes.service-time",
        "puppetlabs.puppetdb.http:name=/pdb/cmd/v1.service-time",
        "puppetlabs.puppetdb.http:name=commands.service-time",
        "puppetlabs.puppetdb.http:name=/pdb/query/v4.200",
    ]
    query, cmd = pick_http_latency_beans(beans)
    assert query == "puppetlabs.puppetdb.http:name=/pdb/query/v4.service-time"
    assert cmd == "puppetlabs.puppetdb.http:name=/pdb/cmd/v1.service-time"
