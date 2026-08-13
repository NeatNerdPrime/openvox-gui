#!/usr/bin/env python3
"""List Puppet environment directory names on a compiler (control_repo branches).

After r10k, each control_repo Git branch is a directory under
/etc/puppetlabs/code/environments/. Dedicated consoles have no codedir;
openvox-gui discovers environments via bolt script run of this helper.

Prints JSON: {"environments": ["production", ...], "codedir": "..."}.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path("/etc/puppetlabs/code/environments")


def main() -> int:
    names: list[str] = []
    if ROOT.is_dir():
        for d in sorted(ROOT.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                names.append(d.name)
    json.dump(
        {"environments": names, "codedir": str(ROOT)},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
