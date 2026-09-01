"""Jolokia population gauges are numbers or {Value: n}."""
from __future__ import annotations

from app.routers.metrics import jmx_scalar


def test_jmx_scalar_number():
    assert jmx_scalar(89) == 89.0
    assert jmx_scalar(412.5) == 412.5


def test_jmx_scalar_composite():
    assert jmx_scalar({"Value": 89}) == 89.0
    assert jmx_scalar({"value": 12}) == 12.0
    assert jmx_scalar({"Count": 3}) == 3.0


def test_jmx_scalar_empty():
    assert jmx_scalar(None) is None
    assert jmx_scalar({}) is None
    assert jmx_scalar(True) is None
