"""Live fleet is active PuppetDB; DNS RR names hidden; ovcompilers stay."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.fleet_insights import (
    apply_report_freshness,
    compute_status_counts,
    display_status,
    downgrade_stale_failed,
    partition_display_nodes,
)
from app.services.puppetdb import PuppetDBService


@pytest.mark.asyncio
async def test_compute_live_nodes_uses_pdb_not_ca():
    svc = PuppetDBService()
    pdb = [
        {"certname": "ovcompilers.atlc-it.corp.int-x.ai", "deactivated": None},
        {"certname": "ovcompiler1.atlc-it.corp.int-x.ai", "deactivated": None},
        {"certname": "ovca.corp.int-x.ai", "deactivated": None},
        {"certname": "ovdb.corp.int-x.ai", "deactivated": None},
    ]
    excluded = {"ovca.corp.int-x.ai", "ovdb.corp.int-x.ai"}

    with patch.object(svc, "get_nodes", new=AsyncMock(return_value=pdb)):
        with patch(
            "app.services.cluster_config.fleet_excluded_certnames",
            return_value=excluded,
        ):
            live = await svc._compute_live_nodes()

    names = {n["certname"] for n in live}
    assert "ovcompilers.atlc-it.corp.int-x.ai" in names
    assert "ovcompiler1.atlc-it.corp.int-x.ai" in names
    assert "ovca.corp.int-x.ai" not in names
    assert "ovdb.corp.int-x.ai" not in names


def test_downgrade_stale_failed_after_eight_hours():
    old = (datetime.utcnow() - timedelta(hours=9)).isoformat() + "Z"
    fresh = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    nodes = [
        {
            "certname": "old.example",
            "latest_report_status": "failed",
            "report_timestamp": old,
        },
        {
            "certname": "fresh.example",
            "latest_report_status": "failed",
            "report_timestamp": fresh,
        },
        {
            "certname": "ok.example",
            "latest_report_status": "unchanged",
            "report_timestamp": old,
        },
    ]
    downgrade_stale_failed(nodes, hours=8.0)
    by_cn = {n["certname"]: n for n in nodes}
    assert by_cn["old.example"]["latest_report_status"] == "unreported"
    assert by_cn["old.example"]["status_source"] == "stale_failed"
    assert by_cn["fresh.example"]["latest_report_status"] == "failed"
    assert by_cn["ok.example"]["latest_report_status"] == "unchanged"


def test_stale_unchanged_becomes_unreported_after_a_day():
    two_days = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
    six_hours = (datetime.utcnow() - timedelta(hours=6)).isoformat() + "Z"
    nodes = [
        {
            "certname": "old-ok.example",
            "latest_report_status": "unchanged",
            "report_timestamp": two_days,
        },
        {
            "certname": "recent-ok.example",
            "latest_report_status": "unchanged",
            "report_timestamp": six_hours,
        },
        {
            "certname": "day-old-failed.example",
            "latest_report_status": "failed",
            "report_timestamp": (datetime.utcnow() - timedelta(hours=25)).isoformat()
            + "Z",
        },
    ]
    apply_report_freshness(nodes, failed_hours=8.0, fresh_hours=24.0)
    by_cn = {n["certname"]: n for n in nodes}
    assert by_cn["old-ok.example"]["latest_report_status"] == "unreported"
    assert by_cn["old-ok.example"]["status_source"] == "stale_report"
    assert by_cn["recent-ok.example"]["latest_report_status"] == "unchanged"
    assert by_cn["day-old-failed.example"]["latest_report_status"] == "unreported"
    assert by_cn["day-old-failed.example"]["status_source"] == "stale_failed"


def test_empty_status_is_unreported_not_unchanged():
    nodes = [
        {"certname": "a", "latest_report_status": None},
        {"certname": "b", "latest_report_status": ""},
        {"certname": "c", "latest_report_status": "unreported"},
        {"certname": "d", "latest_report_status": "unchanged"},
    ]
    assert display_status(nodes[0]) == "unreported"
    assert display_status(nodes[1]) == "unreported"
    counts = compute_status_counts(nodes)
    parts = partition_display_nodes(nodes)
    assert counts["unreported"] == 3
    assert counts["unchanged"] == 1
    assert {n["certname"] for n in parts["unreported"]} == {"a", "b", "c"}
