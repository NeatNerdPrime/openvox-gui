"""Local bcrypt hashing — must work with bcrypt 5 (no passlib)."""
from __future__ import annotations

from pathlib import Path

from app.middleware.auth_local import (
    _hash_password,
    _parse_htpasswd,
    _verify_password_hash,
)


def test_hash_and_verify_round_trip():
    hashed = _hash_password("opensesame")
    assert hashed.startswith("$2")
    assert _verify_password_hash("opensesame", hashed)
    assert not _verify_password_hash("wrong", hashed)


def test_verify_rejects_junk():
    assert not _verify_password_hash("x", "not-a-hash")
    assert not _verify_password_hash("x", "")


def test_long_password_is_truncated_not_raised():
    long = "a" * 200
    hashed = _hash_password(long)
    assert _verify_password_hash(long, hashed)


def test_parse_htpasswd(tmp_path: Path):
    p = tmp_path / "htpasswd"
    p.write_text("# comment\nadmin:$2b$12$abc\nviewer:hash2\n\n", encoding="utf-8")
    assert _parse_htpasswd(p) == {"admin": "$2b$12$abc", "viewer": "hash2"}
