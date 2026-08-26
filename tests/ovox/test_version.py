"""ovox version files stay in lockstep with the GUI root VERSION."""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_ovox_version_files_match_root():
    root = (_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    ovox_file = (_ROOT / "ovox" / "VERSION").read_text(encoding="utf-8").strip()
    init_src = (_ROOT / "ovox" / "ovox" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(init_src)
    pkg_ver = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__version__":
                    if isinstance(node.value, ast.Constant):
                        pkg_ver = node.value.value
    toml = (_ROOT / "ovox" / "pyproject.toml").read_text(encoding="utf-8")
    toml_ver = None
    for line in toml.splitlines():
        if line.startswith("version = "):
            toml_ver = line.split('"', 2)[1]
            break
    assert root
    assert ovox_file == root
    assert pkg_ver == root
    assert toml_ver == root
