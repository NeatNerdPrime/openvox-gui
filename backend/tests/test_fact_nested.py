"""Nested fact extraction for Fact Explorer."""
from __future__ import annotations

from app.routers.facts import get_nested_value


def test_get_nested_value_dict():
    assert get_nested_value({"family": "RedHat", "name": "Rocky"}, "family") == "RedHat"
    assert get_nested_value({"release": {"major": "9"}}, "release.major") == "9"


def test_get_nested_value_json_string():
    raw = '{"family": "RedHat", "release": {"major": "9"}}'
    assert get_nested_value(raw, "family") == "RedHat"
    assert get_nested_value(raw, "release.major") == "9"


def test_get_nested_value_missing():
    assert get_nested_value({"family": "RedHat"}, "architecture") is None
    assert get_nested_value("RedHat", "family") is None
