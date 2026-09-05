"""Dashboard trends must follow PuppetDB report status, not local Bolt overlay."""
from __future__ import annotations

from app.services.fleet_insights import compute_trends


def test_trends_ignore_live_run_overlay():
    nodes = [
        {
            "certname": "web01.example.com",
            "latest_report_status": "unchanged",  # GUI live-run flip
            "pdb_latest_report_status": "failed",
        }
    ]
    reports = [
        {
            "certname": "web01.example.com",
            "status": "failed",
            "noop": False,
            "receive_time": "2026-09-01T12:00:00.000Z",
        }
    ]
    rows = compute_trends(nodes, reports)
    assert rows
    last = rows[-1]
    assert last["failed"] == 1
    assert last["unchanged"] == 0


def test_trends_single_bucket_when_no_reports():
    nodes = [
        {
            "certname": "web01.example.com",
            "pdb_latest_report_status": "unchanged",
        }
    ]
    rows = compute_trends(nodes, [])
    assert len(rows) == 48
    assert rows[-1]["unchanged"] == 1
