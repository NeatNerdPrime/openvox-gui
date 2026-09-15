"""Directory listings for /packages must be scrapeable by install.bash."""
from __future__ import annotations

from app.utils.pkg_static import listing_html


def test_listing_encodes_plus_in_href():
    name = "openvox-agent_8.28.1-1+ubuntu24.04_amd64.deb"
    page = listing_html([name, "index.txt"])
    assert 'href="openvox-agent_8.28.1-1%2Bubuntu24.04_amd64.deb"' in page
    assert name in page
    assert 'href="index.txt"' in page


def test_listing_skips_parent_and_paths():
    page = listing_html(["..", "../etc/passwd", "ok.deb", ""])
    assert ".." not in page
    assert "passwd" not in page
    assert 'href="ok.deb"' in page


def test_packages_filename_is_pool_relative():
    """ATLC/PDXC dists/.../Packages lists pool/ paths, not directory HTML."""
    stanza = (
        "Package: openvox-agent\n"
        "Architecture: amd64\n"
        "Filename: pool/openvox8/o/openvox-agent/"
        "openvox-agent_8.28.1-1+ubuntu24.04_amd64.deb\n"
        "\n"
    )
    assert "pool/openvox8/o/openvox-agent/" in stanza
    assert "ubuntu24.04" in stanza
    assert "amd64" in stanza
