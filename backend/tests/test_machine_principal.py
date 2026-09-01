"""Service-token principals must not require a GUI users row."""
from __future__ import annotations

from app.dependencies import is_machine_principal


def test_service_token_is_machine_even_if_username_is_bolt():
    assert is_machine_principal({
        "user_id": "bolt",
        "username": "bolt",
        "role": "operator",
        "token_type": "service",
    })


def test_local_enc_plugin_is_machine():
    assert is_machine_principal({
        "user_id": "bolt-inventory-local",
        "role": "bolt-inventory-readonly",
        "token_type": "local-loopback",
    })


def test_human_jwt_is_not_machine():
    assert not is_machine_principal({
        "user_id": "jsheets",
        "username": "jsheets",
        "role": "admin",
    })
