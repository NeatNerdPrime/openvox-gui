"""
Pure ENC dict merge — no SQLAlchemy, no FastAPI.

Kept in its own module so unit tests and ENC resolution share one
implementation without pulling the rest of the classification service.
"""
from typing import Dict


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep-merge two dicts. Override wins for scalar values;
    dicts are merged recursively."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
