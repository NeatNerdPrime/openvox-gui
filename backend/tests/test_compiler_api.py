"""Unit tests for compiler HTTP payload parsers."""
from __future__ import annotations

from app.services.puppetserver import (
    parse_environment_classes_payload,
    parse_environment_modules_payload,
    parse_environments_payload,
)


def test_parse_environments_payload():
    data = {
        "search_paths": ["/etc/puppetlabs/code/environments"],
        "environments": {
            "production": {"settings": {}},
            "development": {"settings": {}},
        },
    }
    assert parse_environments_payload(data) == ["development", "production"]
    assert parse_environments_payload({"environments": ["qa", "prod"]}) == ["prod", "qa"]
    assert parse_environments_payload(None) == []
    assert parse_environments_payload({}) == []


def test_parse_environment_classes_payload():
    data = {
        "files": [
            {
                "path": "/etc/puppetlabs/code/environments/production/modules/apache/manifests/init.pp",
                "classes": [{"name": "apache", "params": []}],
            },
            {
                "path": ".../profile/manifests/base.pp",
                "classes": [{"name": "profile::base"}, "profile::linux"],
            },
        ]
    }
    assert parse_environment_classes_payload(data) == [
        "apache",
        "profile::base",
        "profile::linux",
    ]
    assert parse_environment_classes_payload({}) == []


def test_parse_environment_modules_payload():
    data = {
        "modules": {
            "stdlib": {"version": "9.6.0"},
            "apache": {"version": "12.0.0", "author": "puppetlabs"},
        }
    }
    mods = parse_environment_modules_payload(data)
    names = [m["name"] for m in mods]
    assert names == ["apache", "stdlib"]
    assert mods[0]["version"] == "12.0.0"
    assert parse_environment_modules_payload(None) == []
