"""
Fleet status / trend computation (srdevarch1 MP1).

Single home for node status categorization and rolling trends so dashboard,
puppetdb_service, and metrics routers do not diverge.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


def _parse_report_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def downgrade_stale_failed(nodes: List[Dict], hours: float = 8.0) -> List[Dict]:
    """Stop alerting Failed when the last report is older than *hours*.

    A day-old failed report is history, not an incident. Display those
    nodes as unreported so Overview does not stay red. Set hours<=0 to
    disable. Original status is kept in node_index_status.
    """
    return apply_report_freshness(nodes, failed_hours=hours, fresh_hours=0)


def apply_report_freshness(
    nodes: List[Dict],
    failed_hours: float = 8.0,
    fresh_hours: float = 24.0,
) -> List[Dict]:
    """Normalize display status from report age.

    - ``failed`` older than *failed_hours* → unreported (stop alerting).
    - any status older than *fresh_hours* → unreported (not current).
    Hours <= 0 disables that cutoff. Original status stays in
    node_index_status.
    """
    if not nodes:
        return nodes
    now = datetime.utcnow()
    fail_cut = now - timedelta(hours=failed_hours) if failed_hours > 0 else None
    fresh_cut = now - timedelta(hours=fresh_hours) if fresh_hours > 0 else None
    for node in nodes:
        status = (node.get("latest_report_status") or "").lower()
        ts = _parse_report_ts(node.get("report_timestamp"))
        reason = None
        if status == "failed" and fail_cut is not None:
            if ts is None or ts < fail_cut:
                reason = "stale_failed"
        if reason is None and fresh_cut is not None and status and status != "unreported":
            if ts is None or ts < fresh_cut:
                reason = "stale_report"
        if reason:
            node["node_index_status"] = node.get("node_index_status") or (
                status or "failed"
            )
            node["latest_report_status"] = "unreported"
            node["status_source"] = reason
    return nodes


def display_status(node: Dict) -> str:
    """Single display bucket for Overview, Nodes, and Monitoring.

    Empty / unknown latest_report_status is unreported (not unchanged).
    """
    if node.get("latest_report_noop"):
        return "noop"
    status = (node.get("latest_report_status") or "").strip().lower()
    if status in ("failed", "unchanged", "changed", "unreported", "noop"):
        return status
    return "unreported"


def compute_status_counts(nodes: List[Dict]) -> Dict[str, int]:
    """Categorise nodes by display_status (dashboard + Monitoring parity)."""
    counts = {
        "changed": 0,
        "unchanged": 0,
        "failed": 0,
        "unreported": 0,
        "noop": 0,
        "total": len(nodes),
    }
    for node in nodes:
        status = display_status(node)
        counts[status] = counts.get(status, 0) + 1
    return counts


def partition_display_nodes(nodes: List[Dict]) -> Dict[str, List[Dict]]:
    """Same buckets as compute_status_counts, with node rows."""
    out: Dict[str, List[Dict]] = {
        "changed": [],
        "unchanged": [],
        "failed": [],
        "unreported": [],
        "noop": [],
        "compliant": [],
        "drifted": [],
    }
    for node in nodes:
        entry = {
            "certname": node.get("certname"),
            "status": display_status(node),
            "corrective": node.get("latest_report_corrective_change", False),
            "environment": node.get("report_environment"),
            "report_timestamp": node.get("report_timestamp"),
            "status_source": node.get("status_source"),
        }
        st = entry["status"]
        if st in out:
            out[st].append(entry)
        if entry["corrective"] and st != "failed":
            out["drifted"].append(entry)
        elif st in ("unchanged", "changed"):
            out["compliant"].append(entry)
    return out


def compute_trends(nodes: List[Dict], reports: List[Any]) -> List[Dict]:
    """Rolling-state trend computation from pre-fetched nodes + reports."""
    node_state: Dict[str, str] = {}
    for n in nodes:
        cn = n.get("certname", "")
        if not cn:
            continue
        node_state[cn] = display_status(n)

    bucket_reports: Dict[str, list] = defaultdict(list)
    for report in reports:
        ts = (report.get("receive_time") or "")[:13]  # YYYY-MM-DDTHH
        if ts:
            bucket_reports[ts].append(report)

    all_buckets = sorted(bucket_reports.keys())
    if not all_buckets:
        return []

    result = []
    for bucket in all_buckets:
        for report in bucket_reports[bucket]:
            cn = report.get("certname", "")
            if cn not in node_state:
                continue
            if report.get("noop", False):
                node_state[cn] = "noop"
            else:
                node_state[cn] = report.get("status", "unchanged")

        counts = {"unchanged": 0, "changed": 0, "failed": 0, "noop": 0, "unreported": 0}
        for status in node_state.values():
            if status in counts:
                counts[status] += 1
            else:
                counts["unchanged"] += 1
        # Dashboard uses "timestamp"; keep both keys for consumers
        result.append({"timestamp": bucket, "hour": bucket, **counts})
    return result[-48:] if result else result
