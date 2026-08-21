"""VIP / fleet_exclude names must not appear in live fleet membership."""
from __future__ import annotations

from unittest.mock import patch

from app.services.cluster_config import fleet_excluded_certnames, is_fleet_excluded


def test_fleet_excluded_merges_cluster_lists():
    cfg = {
        "deployment_mode": "clustered",
        "ca_vips": ["ovca.corp.example.com"],
        "dns_rr_vips": ["ovdb.corp.example.com"],
        "infra_vips": ["ovcompilers.pdxc-it.corp.example.com"],
        "vip_hosts": ["openvox.corp.example.com"],
        "fleet_exclude": ["extra-lb.example.com"],
        "compilers": [],
        "puppetdb_nodes": [],
        "ca_nodes": [],
        "consoles": [],
        "code_deploy_targets": [],
        "enc_api_urls": [],
        "database_backend": "postgresql",
    }
    with patch("app.services.cluster_config.load_cluster_config", return_value=cfg):
        with patch("app.services.cluster_config.settings") as st:
            st.fleet_exclude = "env-only.example.com"
            xs = fleet_excluded_certnames()
    assert "ovcompilers.pdxc-it.corp.example.com" not in xs
    assert "ovdb.corp.example.com" in xs
    assert "ovca.corp.example.com" in xs
    assert "openvox.corp.example.com" in xs
    assert "extra-lb.example.com" in xs
    assert "env-only.example.com" in xs
    assert not is_fleet_excluded("ovcompilers.pdxc-it.corp.example.com")
    assert not is_fleet_excluded("ovcompiler1.pdxc-it.corp.example.com")
