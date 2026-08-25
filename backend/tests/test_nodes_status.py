"""Unit tests for node status overlay (FQDN vs short name, live-run)."""

from datetime import datetime, timedelta

from app.services.puppetdb import (
    _cert_aliases,
    _report_ts,
    _pick_report_for_node,
    _fold_newest_report,
    _validate_report_hash,
)


def test_validate_report_hash_accepts_sha1_and_sha256():
    sha1 = "85c28c2a766d3b3d0c3c2bfd7aee92589293ecf7"
    sha256 = "a" * 64
    assert _validate_report_hash(sha1) == sha1
    assert _validate_report_hash(sha256.upper()) == sha256
    try:
        _validate_report_hash("not-hex")
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        _validate_report_hash("abc")  # too short
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_report_falls_back_to_prefix():
    from app.services.puppetdb import PuppetDBService
    import asyncio

    svc = PuppetDBService.__new__(PuppetDBService)
    svc._peer_puppetdb_hosts = lambda: []  # type: ignore[method-assign]

    async def fake_query(endpoint, query=None, params=None):
        assert endpoint == "reports"
        assert "85c28c2a" in (query or "")
        return []

    async def fake_get_reports(**kwargs):
        assert "^85c28c2a" in (kwargs.get("query") or "")
        return [{
            "hash": "85c28c2a766d3b3d0c3c2bfd7aee92589293ecf7abcd",
            "status": "unchanged",
        }]

    svc._query = fake_query  # type: ignore[method-assign]
    svc.get_reports = fake_get_reports  # type: ignore[method-assign]

    row = asyncio.run(
        PuppetDBService.get_report(svc, "85c28c2a766d3b3d0c3c2bfd7aee92589293ecf7")
    )
    assert row["hash"].startswith("85c28c2a")
    assert row["status"] == "unchanged"


def test_cert_aliases_fqdn_and_short():
    assert _cert_aliases("ovcompiler1.pdxc-it.corp.int-x.ai") == [
        "ovcompiler1.pdxc-it.corp.int-x.ai",
        "ovcompiler1",
    ]
    assert _cert_aliases("ovcompiler1") == ["ovcompiler1"]
    assert _cert_aliases("") == []
    assert _cert_aliases("  OVCA1.PDXC-IT.CORP.INT-X.AI  ") == [
        "ovca1.pdxc-it.corp.int-x.ai",
        "ovca1",
    ]


def test_report_ts_prefers_receive_time():
    assert _report_ts({"receive_time": "b", "start_time": "a"}) == "b"
    assert _report_ts({"start_time": "a"}) == "a"
    assert _report_ts(None) == ""


def test_pick_report_unique_short_name():
    by_exact = {
        "ovcompiler1": {"status": "unchanged", "receive_time": "2"},
    }
    assert _pick_report_for_node("ovcompiler1.pdxc-it.corp.int-x.ai", by_exact)["status"] == "unchanged"


def test_pick_report_does_not_cross_sites():
    """ovca1.pdxc and ovca1.atlc must not share each other's latest report."""
    by_exact = {
        "ovca1.pdxc-it.corp.int-x.ai": {"status": "unchanged", "receive_time": "1"},
        "ovca1.atlc-it.corp.int-x.ai": {"status": "failed", "receive_time": "9"},
    }
    pdxc = _pick_report_for_node("ovca1.pdxc-it.corp.int-x.ai", by_exact)
    atlc = _pick_report_for_node("ovca1.atlc-it.corp.int-x.ai", by_exact)
    assert pdxc["status"] == "unchanged"
    assert atlc["status"] == "failed"


def test_overlay_picks_newer_short_name_report():
    from app.services.puppetdb import PuppetDBService

    nodes = [
        {
            "certname": "ovcompiler1.pdxc-it.corp.int-x.ai",
            "latest_report_status": "failed",
            "report_timestamp": "2026-08-01T00:00:00Z",
        }
    ]
    svc = PuppetDBService.__new__(PuppetDBService)
    latest = {
        "ovcompiler1": {
            "certname": "ovcompiler1",
            "status": "unchanged",
            "receive_time": "2026-08-13T18:00:00Z",
            "hash": "abc",
            "producer": "ovcompiler2.example",
            "cached_catalog_status": "not_used",
        }
    }

    async def fake_latest():
        return latest

    svc.get_latest_reports_by_certname = fake_latest  # type: ignore[method-assign]

    import asyncio

    asyncio.run(PuppetDBService._overlay_latest_report_status(svc, nodes))
    assert nodes[0]["latest_report_status"] == "unchanged"
    assert nodes[0]["status_source"] == "latest_report"
    assert nodes[0]["node_index_status"] == "failed"


def test_fold_newest_report_prefers_later_success():
    """Stuck latest_report?=failed must lose to a newer unchanged row."""
    out = {}
    _fold_newest_report(
        out,
        {
            "certname": "ovca1.pdxc-it.corp.int-x.ai",
            "status": "failed",
            "receive_time": "2026-08-13T17:00:00Z",
        },
    )
    _fold_newest_report(
        out,
        {
            "certname": "ovca1.pdxc-it.corp.int-x.ai",
            "status": "unchanged",
            "receive_time": "2026-08-13T18:00:00Z",
        },
    )
    assert out["ovca1.pdxc-it.corp.int-x.ai"]["status"] == "unchanged"


def test_fold_newest_report_keeps_sites_apart():
    out = {}
    _fold_newest_report(
        out,
        {
            "certname": "ovca1.pdxc-it.corp.int-x.ai",
            "status": "unchanged",
            "receive_time": "1",
        },
    )
    _fold_newest_report(
        out,
        {
            "certname": "ovca1.atlc-it.corp.int-x.ai",
            "status": "failed",
            "receive_time": "9",
        },
    )
    assert out["ovca1.pdxc-it.corp.int-x.ai"]["status"] == "unchanged"
    assert out["ovca1.atlc-it.corp.int-x.ai"]["status"] == "failed"


def test_get_latest_reports_merges_recent_over_stuck_flag():
    from app.services.puppetdb import PuppetDBService
    import asyncio

    svc = PuppetDBService.__new__(PuppetDBService)

    async def fake_pql(query, limit=5000):
        return [
            {
                "certname": "ovca1.pdxc-it.corp.int-x.ai",
                "status": "failed",
                "receive_time": "2026-08-13T17:00:00Z",
                "hash": "old-failed",
            }
        ]

    async def fake_get_reports(**kwargs):
        return [
            {
                "certname": "ovca1.pdxc-it.corp.int-x.ai",
                "status": "unchanged",
                "receive_time": "2026-08-13T18:05:00Z",
                "hash": "new-ok",
            }
        ]

    svc.pql = fake_pql  # type: ignore[method-assign]
    svc.get_reports = fake_get_reports  # type: ignore[method-assign]
    svc._peer_puppetdb_hosts = lambda: []  # type: ignore[method-assign]

    latest = asyncio.run(PuppetDBService.get_latest_reports_by_certname(svc))
    row = latest["ovca1.pdxc-it.corp.int-x.ai"]
    assert row["status"] == "unchanged"
    assert row["hash"] == "new-ok"


def test_get_newest_report_no_pql_order_by():
    from app.services.puppetdb import PuppetDBService
    import asyncio

    svc = PuppetDBService.__new__(PuppetDBService)
    seen = {}

    async def fake_get_reports(query=None, limit=50, order_by="receive_time", order_dir="desc"):
        seen["query"] = query
        seen["order_by"] = order_by
        return [
            {
                "certname": "ovca1.pdxc-it.corp.int-x.ai",
                "status": "failed",
                "receive_time": "2026-08-13T17:00:00Z",
            },
            {
                "certname": "ovca1.pdxc-it.corp.int-x.ai",
                "status": "unchanged",
                "receive_time": "2026-08-13T18:00:00Z",
            },
        ]

    svc.get_reports = fake_get_reports  # type: ignore[method-assign]
    svc._peer_puppetdb_hosts = lambda: []  # type: ignore[method-assign]
    row = asyncio.run(
        PuppetDBService.get_newest_report_for_certname(
            svc, "ovca1.pdxc-it.corp.int-x.ai"
        )
    )
    assert "order by" not in (seen.get("query") or "").lower()
    assert row["status"] == "unchanged"


def test_get_latest_reports_merges_newer_peer_row():
    from app.services.puppetdb import PuppetDBService
    import asyncio

    svc = PuppetDBService.__new__(PuppetDBService)

    async def fake_pql(query, limit=5000):
        return [
            {
                "certname": "agent.example.com",
                "status": "unchanged",
                "receive_time": "2026-08-23T10:00:00Z",
                "hash": "local-old",
            }
        ]

    async def fake_get_reports(**kwargs):
        return []

    async def fake_from_host(host):
        assert host == "ovdb.site-b.example.com"
        return {
            "agent.example.com": {
                "certname": "agent.example.com",
                "status": "unchanged",
                "receive_time": "2026-08-25T11:00:00Z",
                "hash": "peer-new",
            }
        }

    svc.pql = fake_pql  # type: ignore[method-assign]
    svc.get_reports = fake_get_reports  # type: ignore[method-assign]
    svc._peer_puppetdb_hosts = lambda: ["ovdb.site-b.example.com"]  # type: ignore[method-assign]
    svc._latest_reports_from_host = fake_from_host  # type: ignore[method-assign]

    latest = asyncio.run(PuppetDBService.get_latest_reports_by_certname(svc))
    row = latest["agent.example.com"]
    assert row["hash"] == "peer-new"
    assert row["_openvoxdb_source"] == "ovdb.site-b.example.com"


def test_peer_hosts_include_console_site_ovdb():
    from unittest.mock import patch
    from app.services.puppetdb import PuppetDBService, settings

    def fake_cfg():
        return {
            "puppetdb_nodes": ["ovdb1.site-a.example.com"],
            "dns_rr_vips": ["ovdb.site-a.example.com"],
            "consoles": [
                "openvox.site-a.example.com",
                "openvox.site-b.example.com",
            ],
        }

    with patch.object(settings, "puppetdb_host", "ovdb.example.com"):
        with patch.object(settings, "puppetdb_peers", "ovdb.extra.example.com"):
            with patch(
                "app.services.cluster_config.load_cluster_config",
                fake_cfg,
            ):
                hosts = PuppetDBService._peer_puppetdb_hosts(
                    PuppetDBService.__new__(PuppetDBService)
                )
    assert "ovdb.extra.example.com" in hosts
    assert "ovdb1.site-a.example.com" in hosts
    assert "ovdb.site-a.example.com" in hosts
    assert "ovdb.site-b.example.com" in hosts
    assert "ovdb.example.com" not in hosts


def test_apply_live_run_flips_stale_failed():
    from unittest.mock import AsyncMock, MagicMock
    import asyncio
    from app.routers import nodes as nodes_mod

    class Row:
        def __init__(self):
            self.node_name = "ovcompiler1"
            self.executed_at = datetime.utcnow()
            self.status = "success"
            self.command_name = "/opt/puppetlabs/bin/puppet agent -t"

    result = MagicMock()
    result.scalars.return_value.all.return_value = [Row()]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    node = {
        "certname": "ovcompiler1.pdxc-it.corp.int-x.ai",
        "latest_report_status": "failed",
        "report_timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
    }
    asyncio.run(nodes_mod.apply_live_run_status([node], db))
    assert node["latest_report_status"] == "unchanged"
    assert node["status_source"] == "live_run"
