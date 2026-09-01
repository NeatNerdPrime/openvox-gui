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
        {"certname": "ovcompilers.atlc-it.example.com", "deactivated": None},
        {"certname": "ovcompiler1.atlc-it.example.com", "deactivated": None},
        {"certname": "ovca.example.com", "deactivated": None},
        {"certname": "ovdb.example.com", "deactivated": None},
    ]
    excluded = {"ovca.example.com", "ovdb.example.com"}

    with patch.object(svc, "get_nodes", new=AsyncMock(return_value=pdb)):
        with patch(
            "app.services.cluster_config.fleet_excluded_certnames",
            return_value=excluded,
        ):
            with patch(
                "app.services.dismissed_nodes.dismissed_certnames",
                new=AsyncMock(return_value=set()),
            ):
                live = await svc._compute_live_nodes()

    names = {n["certname"] for n in live}
    assert "ovcompilers.atlc-it.example.com" in names
    assert "ovcompiler1.atlc-it.example.com" in names
    assert "ovca.example.com" not in names
    assert "ovdb.example.com" not in names


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
    assert by_cn["old.example"]["latest_report_status"] == "failed"
    assert by_cn["old.example"]["report_stale"] is True
    assert by_cn["old.example"]["freshness_reason"] == "stale_failed"
    assert by_cn["fresh.example"]["latest_report_status"] == "failed"
    assert by_cn["fresh.example"]["report_stale"] is False
    assert by_cn["ok.example"]["latest_report_status"] == "unchanged"


def test_stale_report_keeps_pdb_status():
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
    assert by_cn["old-ok.example"]["latest_report_status"] == "unchanged"
    assert by_cn["old-ok.example"]["report_stale"] is True
    assert by_cn["old-ok.example"]["freshness_reason"] == "stale_report"
    assert by_cn["recent-ok.example"]["latest_report_status"] == "unchanged"
    assert by_cn["recent-ok.example"]["report_stale"] is False
    assert by_cn["day-old-failed.example"]["latest_report_status"] == "failed"
    assert by_cn["day-old-failed.example"]["freshness_reason"] == "stale_failed"


@pytest.mark.asyncio
async def test_compute_live_nodes_keeps_day_old_unchanged():
    two_days = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
    pdb = [
        {
            "certname": "agent.example.com",
            "latest_report_status": "unchanged",
            "report_timestamp": two_days,
            "deactivated": None,
        },
    ]
    with patch.object(PuppetDBService, "get_nodes", new=AsyncMock(return_value=pdb)):
        with patch(
            "app.services.cluster_config.fleet_excluded_certnames",
            return_value=set(),
        ):
            with patch(
                "app.services.dismissed_nodes.dismissed_certnames",
                new=AsyncMock(return_value=set()),
            ):
                live = await PuppetDBService()._compute_live_nodes()
    assert live[0]["latest_report_status"] == "unchanged"
    assert live[0]["report_stale"] is True


@pytest.mark.asyncio
async def test_compute_live_nodes_hides_dismissed_ghosts():
    svc = PuppetDBService()
    pdb = [
        {"certname": "alive.example.com", "deactivated": None},
        {"certname": "ghost.example.com", "deactivated": None},
    ]
    with patch.object(svc, "get_nodes", new=AsyncMock(return_value=pdb)):
        with patch(
            "app.services.cluster_config.fleet_excluded_certnames",
            return_value=set(),
        ):
            with patch(
                "app.services.dismissed_nodes.dismissed_certnames",
                new=AsyncMock(return_value={"ghost.example.com"}),
            ):
                live = await svc._compute_live_nodes()
    names = {n["certname"] for n in live}
    assert "alive.example.com" in names
    assert "ghost.example.com" not in names


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
