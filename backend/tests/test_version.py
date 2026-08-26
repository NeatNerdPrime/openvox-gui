"""Root VERSION is the single source of truth for the backend package."""
from pathlib import Path

from app import __version__

_ROOT = Path(__file__).resolve().parents[2]


def test_backend_version_matches_root_file():
    asserted = (_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert asserted, "VERSION file is empty"
    assert __version__ == asserted


def test_version_is_pep440_shaped():
    # Stable: 3.12.0   Pre-release: 3.12.1-dev.3 / 3.12.0-rc.1
    assert __version__[0].isdigit()
    assert "gamma" not in __version__.lower()
