"""Unit tests for trusted-facts extraction from signed certificates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ObjectIdentifier

# Import service module via package path when available; fall back to path load.
try:
    from app.services import certificates_service as cs
except ImportError:
    import importlib.util
    import sys

    _ROOT = Path(__file__).resolve().parents[1]
    # Load with package-style name so relative imports inside the module work
    # if needed — certificates_service only imports ..utils.sudo at call time
    # for sudo paths; pure decode/extract paths do not need it.
    sys.path.insert(0, str(_ROOT))
    from app.services import certificates_service as cs  # type: ignore


def _make_cert_with_extensions(cn: str, oid_values: dict[str, bytes]) -> bytes:
    """Build a short-lived self-signed PEM with the given OID → DER values."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
    )
    for oid_str, der_val in oid_values.items():
        builder = builder.add_extension(
            x509.UnrecognizedExtension(ObjectIdentifier(oid_str), der_val),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM)


def _utf8_der(s: str) -> bytes:
    encoded = s.encode("utf-8")
    assert len(encoded) < 128
    return bytes([0x0C, len(encoded)]) + encoded


def test_decode_extension_value_utf8string():
    assert cs.decode_extension_value(_utf8_der("webserver")) == "webserver"
    assert cs.decode_extension_value(_utf8_der("prod")) == "prod"


def test_decode_extension_value_printable():
    raw = bytes([0x13, 0x03]) + b"abc"
    assert cs.decode_extension_value(raw) == "abc"


def test_extract_trusted_extensions_maps_pp_role():
    pem = _make_cert_with_extensions(
        "web01.example.com",
        {
            "1.3.6.1.4.1.34380.1.1.13": _utf8_der("webserver"),
            "1.3.6.1.4.1.34380.1.1.12": _utf8_der("production"),
            "1.3.6.1.4.1.34380.1.1.19": _utf8_der("dc1"),
            # Non-Puppet OID must be ignored (do not use 2.5.29.19 —
            # cryptography 50 parses that as BasicConstraints).
            "1.2.3.4.5": _utf8_der("ignore-me"),
        },
    )
    # Note: BasicConstraints is a standard OID; our UnrecognizedExtension with
    # 2.5.29.19 is still under a non-Puppet prefix and is filtered out.
    exts = cs.extract_trusted_extensions_from_pem(pem)
    assert exts["pp_role"] == "webserver"
    assert exts["pp_environment"] == "production"
    assert exts["pp_datacenter"] == "dc1"
    assert "ignore-me" not in exts.values()
    assert all(not k.startswith("2.5.") for k in exts)


def test_extract_unknown_puppet_oid_keeps_dotted_form():
    custom_oid = "1.3.6.1.4.1.34380.1.2.99"
    pem = _make_cert_with_extensions(
        "app01.example.com",
        {custom_oid: _utf8_der("custom-value")},
    )
    exts = cs.extract_trusted_extensions_from_pem(pem)
    assert exts[custom_oid] == "custom-value"


def test_custom_oid_mapping_overlay(tmp_path: Path):
    mapping_file = tmp_path / "custom_trusted_oid_mapping.yaml"
    mapping_file.write_text(
        "---\noid_mapping:\n  '1.3.6.1.4.1.34380.1.2.99':\n"
        "    shortname: 'my_app_tier'\n    longname: 'Application Tier'\n",
        encoding="utf-8",
    )
    oid_map, sources = cs.load_oid_mapping(extra_paths=[mapping_file])
    assert oid_map["1.3.6.1.4.1.34380.1.2.99"] == "my_app_tier"
    assert any("custom_trusted_oid_mapping.yaml" in s for s in sources)

    pem = _make_cert_with_extensions(
        "app01.example.com",
        {"1.3.6.1.4.1.34380.1.2.99": _utf8_der("frontend")},
    )
    exts = cs.extract_trusted_extensions_from_pem(pem, oid_map=oid_map)
    assert exts["my_app_tier"] == "frontend"


@pytest.mark.asyncio
async def test_get_trusted_facts_scan_and_filter(tmp_path: Path):
    signed = tmp_path / "signed"
    signed.mkdir()

    pem_web = _make_cert_with_extensions(
        "web01.example.com",
        {
            "1.3.6.1.4.1.34380.1.1.13": _utf8_der("webserver"),
            "1.3.6.1.4.1.34380.1.1.12": _utf8_der("production"),
        },
    )
    pem_db = _make_cert_with_extensions(
        "db01.example.com",
        {"1.3.6.1.4.1.34380.1.1.13": _utf8_der("database")},
    )
    # Cert with no Puppet extensions
    pem_plain = _make_cert_with_extensions("plain.example.com", {})

    (signed / "web01.example.com.pem").write_bytes(pem_web)
    (signed / "db01.example.com.pem").write_bytes(pem_db)
    (signed / "plain.example.com.pem").write_bytes(pem_plain)

    # Full scan (with extensions only)
    result = await cs.get_trusted_facts(
        use_cache=False,
        only_with_extensions=True,
        signed_dir=signed,
    )
    assert result["total_signed"] == 3
    assert result["with_extensions"] == 2
    assert result["without_extensions"] == 1
    assert result["filtered_count"] == 2
    assert "pp_role" in result["extension_keys"]
    assert result["summary"]["pp_role"]["webserver"] == 1
    assert result["summary"]["pp_role"]["database"] == 1

    # Filter by key+value
    filtered = await cs.get_trusted_facts(
        use_cache=False,
        key="pp_role",
        value="webserver",
        only_with_extensions=True,
        signed_dir=signed,
    )
    assert filtered["filtered_count"] == 1
    assert filtered["nodes"][0]["certname"] == "web01.example.com"

    # Include nodes without extensions
    all_nodes = await cs.get_trusted_facts(
        use_cache=False,
        only_with_extensions=False,
        signed_dir=signed,
    )
    assert all_nodes["filtered_count"] == 3
