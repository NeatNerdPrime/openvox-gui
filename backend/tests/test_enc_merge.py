"""ENC deep_merge unit tests — imports the real function (no SQLAlchemy)."""

from app.services.enc_merge import deep_merge


def test_deep_merge_scalar_override():
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_deep_merge_preserves_base_keys():
    assert deep_merge({"a": 1, "b": 2}, {"a": 9}) == {"a": 9, "b": 2}


def test_deep_merge_nested_dicts():
    base = {"classes": {"ntp": {"servers": ["a"]}, "ssh": {}}}
    override = {"classes": {"ntp": {"servers": ["b"]}}}
    out = deep_merge(base, override)
    assert out["classes"]["ntp"]["servers"] == ["b"]
    assert "ssh" in out["classes"]


def test_deep_merge_override_replaces_non_dict():
    assert deep_merge({"x": {"y": 1}}, {"x": "scalar"}) == {"x": "scalar"}


def test_deep_merge_matches_source_file_signature():
    """Guard: merge lives in enc_merge.py so tests skip SQLAlchemy."""
    from pathlib import Path
    merge_src = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "enc_merge.py"
    ).read_text()
    enc_src = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "enc.py"
    ).read_text()
    assert "def deep_merge(base: Dict, override: Dict)" in merge_src
    assert "dicts are merged recursively" in merge_src or "merged recursively" in merge_src
    assert "from .enc_merge import deep_merge" in enc_src
