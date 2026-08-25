"""VIP / fleet_exclude names must not appear in live fleet membership."""
from __future__ import annotations

from unittest.mock import patch

from app.services.cluster_config import (
    fleet_excluded_certnames,
    is_compiler_haproxy_agent,
    is_fleet_excluded,
)


def test_cluster_update_omitted_dns_rr_vips_is_none():
    """Save must not default dns_rr_vips to [] (that wiped ovdb.corp)."""
    from app.routers.config import ClusterConfigUpdate

    body = ClusterConfigUpdate(deployment_mode="single")
    assert body.dns_rr_vips is None
    assert body.ca_vips is None


def test_fleet_excluded_merges_cluster_lists():
    cfg = {
        "deployment_mode": "clustered",
        "ca_vips": ["ovca.corp.example.com"],
        "dns_rr_vips": ["ovdb.corp.example.com"],
        "infra_vips": ["ovcompilers.pdxc-it.corp.example.com"],
        "vip_hosts": ["openvox.corp.example.com"],
        "fleet_exclude": ["extra-lb.example.com", "ovcompilers.iad-it.corp.example.com"],
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
    assert "ovcompilers.iad-it.corp.example.com" not in xs
    assert not is_fleet_excluded("ovcompilers.pdxc-it.corp.example.com")
    assert not is_fleet_excluded("ovcompiler1.pdxc-it.corp.example.com")
    assert is_compiler_haproxy_agent("ovcompilers.iad-it.corp.example.com")
    assert not is_compiler_haproxy_agent("ovca.corp.example.com")
