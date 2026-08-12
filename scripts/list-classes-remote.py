#!/usr/bin/env python3
"""Discover Puppet classes from a live environment on a compiler.

Prints JSON: {"environment": "...", "classes": ["role::foo", ...]}.
Used by openvox-gui ENC available-classes via bolt script run when the
console has no local codedir and /puppet/v3/environment_classes is
unavailable (auth or VIP).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ENV = (sys.argv[1] if len(sys.argv) > 1 else "production").strip() or "production"
ROOT = pathlib.Path("/etc/puppetlabs/code/environments") / ENV
CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_][\w:]*)", re.MULTILINE)


def discover(modules_dir: pathlib.Path) -> list[str]:
    names: list[str] = []
    if not modules_dir.is_dir():
        return names
    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        manifests = mod_dir / "manifests"
        if not manifests.is_dir():
            continue
        for pp in manifests.rglob("*.pp"):
            try:
                text = pp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in CLASS_RE.finditer(text):
                names.append(m.group(1))
    return names


def main() -> int:
    classes: list[str] = []
    if ROOT.is_dir():
        for sub in ("modules", "site-modules", "site", "site_modules"):
            classes.extend(discover(ROOT / sub))
    out = sorted(set(classes))
    json.dump(
        {"environment": ENV, "classes": out, "codedir": str(ROOT)},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
