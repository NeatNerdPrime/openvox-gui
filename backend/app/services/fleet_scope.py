"""
Fleet metric scopes for Insights (location fact + certname REGEX packs).

Resolves a scope id or explicit filters into a set of certnames drawn from
the live fleet (active PuppetDB). Used by Compliance,
Performance, and the Monitoring wallboard.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .puppetdb import puppetdb_service

logger = logging.getLogger(__name__)

# Named REGEX packs — "like things" (OpenVox control plane).
# Applied to certname (case-insensitive).
BUILTIN_PACKS: Dict[str, Dict[str, str]] = {
    "infra": {
        "label": "OpenVox control plane",
        "pattern": r"^(ovcompiler|ovca|ovdb|openvox)[.-]",
    },
    "compilers": {
        "label": "Compilers",
        "pattern": r"^ovcompiler",
    },
    "ca": {
        "label": "Certificate Authority",
        "pattern": r"^ovca",
    },
    "ovdb": {
        "label": "OpenVoxDB",
        "pattern": r"^ovdb",
    },
    "consoles": {
        "label": "GUI consoles",
        "pattern": r"^openvox[.-]",
    },
    "agents": {
        "label": "Agents (non-infra)",
        # Everything on the live fleet that is NOT control-plane naming.
        "pattern": r"^(?!(ovcompiler|ovca|ovdb|openvox)[.-])",
    },
}


@dataclass
class ScopeResult:
    """Resolved host set for a metric query."""

    scope_id: str
    label: str
    kind: str  # all | location | pack | custom | regex
    certnames: Set[str] = field(default_factory=set)
    location: Optional[str] = None
    certname_re: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.certnames)

    def contains(self, certname: str) -> bool:
        if not certname:
            return False
        return certname.strip().lower() in self.certnames

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "label": self.label,
            "kind": self.kind,
            "total": self.total,
            "location": self.location,
            "certname_re": self.certname_re,
            "certnames": sorted(self.certnames),
        }


def _norm_cn(cn: str) -> str:
    return (cn or "").strip().lower()


async def _live_certnames() -> Set[str]:
    nodes = await puppetdb_service.get_live_nodes()
    return {
        _norm_cn(n.get("certname", ""))
        for n in nodes
        if n.get("certname")
    }


async def _location_by_certname() -> Dict[str, str]:
    """Map certname → location fact value (uppercased when present)."""
    try:
        facts = await puppetdb_service._query(
            "facts",
            query='["=", "name", "location"]',
        ) or []
    except Exception as e:
        logger.warning("fleet_scope: location facts query failed: %s", e)
        return {}
    out: Dict[str, str] = {}
    for row in facts:
        cn = _norm_cn(row.get("certname", ""))
        val = row.get("value")
        if not cn or val is None:
            continue
        s = str(val).strip()
        if s:
            out[cn] = s.upper() if s.isalpha() or s.isalnum() else s
    return out


async def list_scopes() -> Dict[str, Any]:
    """Catalog of scopes for the UI (built-in packs + live locations)."""
    live = await _live_certnames()
    loc_map = await _location_by_certname()

    scopes: List[Dict[str, Any]] = [
        {
            "id": "all",
            "label": "All live fleet",
            "kind": "all",
            "count": len(live),
        }
    ]

    for pack_id, meta in BUILTIN_PACKS.items():
        try:
            cre = re.compile(meta["pattern"], re.IGNORECASE)
        except re.error:
            continue
        count = sum(1 for cn in live if cre.search(cn))
        scopes.append({
            "id": f"pack:{pack_id}",
            "label": meta["label"],
            "kind": "pack",
            "pattern": meta["pattern"],
            "count": count,
        })

    # Distinct locations with at least one live host that has the fact
    loc_counts: Dict[str, int] = {}
    for cn in live:
        loc = loc_map.get(cn)
        if not loc:
            continue
        loc_counts[loc] = loc_counts.get(loc, 0) + 1
    for loc in sorted(loc_counts.keys()):
        scopes.append({
            "id": f"location:{loc}",
            "label": f"Location {loc}",
            "kind": "location",
            "location": loc,
            "count": loc_counts[loc],
        })

    scopes.append({
        "id": "custom",
        "label": "Custom selection…",
        "kind": "custom",
        "count": None,
    })

    return {
        "scopes": scopes,
        "live_total": len(live),
        "locations": sorted(loc_counts.keys()),
        "packs": [
            {"id": k, "label": v["label"], "pattern": v["pattern"]}
            for k, v in BUILTIN_PACKS.items()
        ],
    }


async def resolve_scope(
    scope: Optional[str] = None,
    location: Optional[str] = None,
    certname_re: Optional[str] = None,
    certnames: Optional[List[str]] = None,
) -> ScopeResult:
    """Resolve query params to a set of live certnames.

    Precedence:
      1. scope=location:ATLC | pack:compilers | all | custom
      2. Explicit location= / certname_re= / certnames= if scope is all/empty
    """
    live = await _live_certnames()
    scope = (scope or "all").strip()
    location = (location or "").strip() or None
    certname_re = (certname_re or "").strip() or None
    custom = {_norm_cn(c) for c in (certnames or []) if c and c.strip()}

    # Parse composite scope ids
    kind = "all"
    pack_id: Optional[str] = None
    loc_filter: Optional[str] = None
    pattern: Optional[str] = certname_re
    label = "All live fleet"
    scope_id = scope or "all"

    if scope.startswith("location:"):
        kind = "location"
        loc_filter = scope.split(":", 1)[1].strip().upper()
        label = f"Location {loc_filter}"
        scope_id = f"location:{loc_filter}"
    elif scope.startswith("pack:"):
        kind = "pack"
        pack_id = scope.split(":", 1)[1].strip().lower()
        meta = BUILTIN_PACKS.get(pack_id)
        if not meta:
            raise ValueError(f"Unknown pack: {pack_id}")
        pattern = meta["pattern"]
        label = meta["label"]
        scope_id = f"pack:{pack_id}"
    elif scope == "custom" or custom:
        kind = "custom"
        label = "Custom selection"
        scope_id = "custom"
    elif scope in BUILTIN_PACKS:
        kind = "pack"
        pack_id = scope
        meta = BUILTIN_PACKS[pack_id]
        pattern = meta["pattern"]
        label = meta["label"]
        scope_id = f"pack:{pack_id}"
    elif scope not in ("all", "", "none"):
        # Treat bare string as regex if it looks like one
        if any(ch in scope for ch in r"^$*+?[]()|\\"):
            kind = "regex"
            pattern = scope
            label = f"Regex /{scope}/"
            scope_id = f"regex:{scope}"
        else:
            # unknown id → all
            scope_id = "all"
            kind = "all"
            label = "All live fleet"

    # Explicit overrides from query params
    if location and kind in ("all", "location"):
        kind = "location"
        loc_filter = location.strip().upper()
        label = f"Location {loc_filter}"
        scope_id = f"location:{loc_filter}"
    if certname_re and kind == "all":
        kind = "regex"
        pattern = certname_re
        label = f"Regex /{certname_re}/"
        scope_id = f"regex:{certname_re}"

    result_set = set(live)

    if kind == "custom":
        result_set = {c for c in custom if c in live}
        label = f"Custom ({len(result_set)} hosts)"
    else:
        if loc_filter:
            loc_map = await _location_by_certname()
            result_set = {
                cn for cn in result_set
                if loc_map.get(cn, "").upper() == loc_filter.upper()
            }
        if pattern:
            try:
                cre = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"Invalid certname regex: {e}") from e
            result_set = {cn for cn in result_set if cre.search(cn)}
        if custom and kind != "custom":
            # optional further intersect
            result_set &= custom

    return ScopeResult(
        scope_id=scope_id,
        label=label,
        kind=kind,
        certnames=result_set,
        location=loc_filter,
        certname_re=pattern,
    )


def filter_nodes_by_scope(nodes: List[Dict], scope: ScopeResult) -> List[Dict]:
    return [
        n for n in nodes
        if scope.contains(str(n.get("certname", "")))
    ]


def filter_reports_by_scope(reports: List[Dict], scope: ScopeResult) -> List[Dict]:
    return [
        r for r in reports
        if scope.contains(str(r.get("certname", "")))
    ]
