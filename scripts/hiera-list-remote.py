#!/usr/bin/env python3
"""List environment hiera.yaml + data/hieradata YAML on a compiler.

Printed as one JSON object on stdout. Used by openvox-gui Data | Hiera
Data Files via ``bolt script run`` so dedicated consoles (no control
repo) can read the live codedir. Do not invent a local hiera.yaml.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path("/etc/puppetlabs/code/environments")
MAX_FILE = 512 * 1024  # 512 KiB per file; skip monsters


def _read(path: pathlib.Path) -> str:
    if path.stat().st_size > MAX_FILE:
        return f"(skipped: file larger than {MAX_FILE} bytes)"
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    environments = []
    if ROOT.is_dir():
        for env_dir in sorted(ROOT.iterdir()):
            if not env_dir.is_dir() or env_dir.name.startswith("."):
                continue
            files = []
            hiera = env_dir / "hiera.yaml"
            if hiera.is_file():
                files.append({
                    "name": "hiera.yaml",
                    "path": str(hiera),
                    "content": _read(hiera),
                })
            for sub in ("data", "hieradata"):
                data_dir = env_dir / sub
                if not data_dir.is_dir():
                    continue
                found = sorted(data_dir.rglob("*.yaml")) + sorted(data_dir.rglob("*.yml"))
                for yaml_file in found:
                    if not yaml_file.is_file():
                        continue
                    rel = yaml_file.relative_to(data_dir)
                    files.append({
                        "name": f"{sub}/{rel}",
                        "path": str(yaml_file),
                        "content": _read(yaml_file),
                    })
            if files:
                environments.append({
                    "environment": env_dir.name,
                    "files": files,
                })
    json.dump(
        {
            "codedir": str(ROOT),
            "environments": environments,
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
