"""certops role + server-cert protection (GUI user roles)."""
from unittest.mock import MagicMock, patch


def test_valid_user_roles_include_certops():
    from app.dependencies import (
        VALID_USER_ROLES,
        VALID_USER_ROLES_SET,
        READ_ROLES,
        CERT_MUTATE_ROLES,
        is_valid_user_role,
    )

    assert "certops" in VALID_USER_ROLES
    assert "certops" in VALID_USER_ROLES_SET
    assert "certops" in READ_ROLES
    assert "certops" in CERT_MUTATE_ROLES
    # certops may not sign CSRs — sign stays admin/operator only
    assert is_valid_user_role("certops")
    assert is_valid_user_role("admin")
    assert not is_valid_user_role("superuser")
    assert not is_valid_user_role("")


def test_is_protected_certname_from_puppet_conf():
    from app.services import certificates_service as cs

    mock_settings = MagicMock()
    mock_settings.puppet_ssl_cert = "/etc/puppetlabs/puppet/ssl/certs/openvox.example.com.pem"
    mock_settings.puppet_server_host = "ovcompilers.example.com"

    mock_cfg = {
        "deployment_mode": "clustered",
        "consoles": ["openvox.example.com"],
        "compilers": ["ovcompiler1.example.com"],
        "ca_nodes": ["ovca1.example.com"],
        "puppetdb_nodes": ["ovdb1.example.com"],
        "ca_vips": ["ovca.example.com"],
        "code_deploy_targets": [],
    }

    with patch("app.config.settings", mock_settings), \
         patch("app.services.cluster_config.load_cluster_config", return_value=mock_cfg):
        identities = {i["name"]: i["role"] for i in cs.get_protected_identities()}
        protected = cs.get_protected_certnames()

        assert identities["openvox.example.com"] == "console"
        assert identities["ovcompiler1.example.com"] == "compiler"
        assert identities["ovca1.example.com"] == "ca"
        assert identities["ovdb1.example.com"] == "puppetdb"
        assert "ovca.example.com" not in protected
        assert "ovcompilers.example.com" not in protected
        assert "puppet" not in protected
        assert cs.is_protected_certname("openvox.example.com")
        assert cs.is_protected_certname("OpenVox.Example.COM")
        assert not cs.is_protected_certname("agent1.example.com")


def test_localhost_not_protected_from_host_setting_alone():
    from app.services import certificates_service as cs

    mock_settings = MagicMock()
    mock_settings.puppet_ssl_cert = "/etc/puppetlabs/puppet/ssl/certs/localhost.pem"
    mock_settings.puppet_server_host = "localhost"

    mock_svc = MagicMock()
    mock_svc.read_puppet_conf.return_value = {"main": {}}

    with patch("app.config.settings", mock_settings), \
         patch("app.services.cluster_config.load_cluster_config", return_value={
             "deployment_mode": "single",
             "consoles": [],
             "compilers": [],
             "ca_nodes": [],
             "puppetdb_nodes": [],
         }):
        protected = cs.get_protected_certnames()

    assert "localhost" not in protected
