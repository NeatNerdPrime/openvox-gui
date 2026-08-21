"""Live fleet is active PuppetDB; DNS RR names hidden; ovcompilers stay."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.fleet_insights import downgrade_stale_failed
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
