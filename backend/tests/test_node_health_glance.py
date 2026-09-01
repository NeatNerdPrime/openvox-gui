"""Unit tests for Node Detail health-glance fact normalization."""
from __future__ import annotations

from app.services.node_health_glance import (
    facts_to_glance,
    _fact_saturation_hint,
    _skip_glance_mount,
)


def test_facts_to_glance_structured_memory_and_mounts():
    facts = {
        "memory": {
            "system": {
                "total": "15.63 GiB",
                "total_bytes": 16785000000,
                "available": "4.20 GiB",
                "available_bytes": 4509715660,
                "capacity": "73.12%",
            },
            "swap": {"total": "2.00 GiB", "capacity": "0%"},
        },
        "system_uptime": {"days": 12, "hours": 3, "seconds": 1040400, "uptime": "12 days"},
        "processors": {"count": 8, "physicalcount": 4, "models": ["Intel(R) Xeon(R)"]},
        "disks": {"sda": {"size": "100.00 GiB", "size_bytes": 107374182400}},
        "mountpoints": {
            "/": {
                "size": "50.00 GiB",
                "size_bytes": 53687091200,
                "available": "10.00 GiB",
                "available_bytes": 10737418240,
                "used_bytes": 42949672960,
                "capacity": "80.00%",
                "filesystem": "xfs",
            },
            "/var": {
                "size": "20.00 GiB",
                "available": "1.00 GiB",
                "capacity": "95%",
                "filesystem": "xfs",
            },
            "/var/run": {
                "size": "1.00 GiB",
                "available": "0",
                "capacity": "100%",
                "filesystem": "tmpfs",
            },
            "/run": {
                "size": "1.00 GiB",
                "capacity": "100%",
                "filesystem": "tmpfs",
            },
        },
        "load_averages": {"1m": 0.42, "5m": 0.55, "15m": 0.60},
        "os": {"name": "RedHat", "release": {"full": "9.4"}},
        "is_virtual": False,
    }
    g = facts_to_glance(facts)
    assert g["memory"]["used_pct"] == 73.12
    assert "15.63" in (g["memory"]["total"] or "")
    assert g["uptime"]["display"]
    assert g["cpu"]["count"] == 8
    assert g["load"]["load1"] == 0.42
    assert any(m["path"] == "/" for m in g["mounts"])
    assert all(m["path"] not in ("/var/run", "/run") for m in g["mounts"])
    sat = _fact_saturation_hint(g)
    assert sat["level"] in ("yellow", "red")  # /var at 95%


def test_facts_to_glance_legacy_scalars():
    facts = {
        "memorysize": "7.60 GiB",
        "memorysize_mb": "7782.43",
        "memoryfree_mb": "1200.00",
        "uptime": "3 days",
        "processorcount": 2,
    }
    g = facts_to_glance(facts)
    assert g["memory"]["used_pct"] is not None
    assert g["uptime"]["display"] == "3 days"
    assert g["cpu"]["count"] == 2


def test_skip_glance_mount_var_run_and_tmpfs():
    assert _skip_glance_mount("/var/run", "tmpfs")
    assert _skip_glance_mount("/run/user/0", "tmpfs")
    assert not _skip_glance_mount("/var", "xfs")
    assert not _skip_glance_mount("/", "ext4")
