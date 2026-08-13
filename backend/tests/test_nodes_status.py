"""Unit tests for node status overlay (FQDN vs short name, live-run)."""

from datetime import datetime, timedelta

from app.services.puppetdb import _cert_aliases, _report_ts, _pick_report_for_node


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

    asyncio.get_event_loop().run_until_complete(
        PuppetDBService._overlay_latest_report_status(svc, nodes)
    )
    assert nodes[0]["latest_report_status"] == "unchanged"
    assert nodes[0]["status_source"] == "latest_report"
    assert nodes[0]["node_index_status"] == "failed"


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
    asyncio.get_event_loop().run_until_complete(
        nodes_mod.apply_live_run_status([node], db)
    )
    assert node["latest_report_status"] == "unchanged"
    assert node["status_source"] == "live_run"
