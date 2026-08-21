"""Live fleet is active PuppetDB; DNS RR names hidden; ovcompilers stay."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.puppetdb import PuppetDBService


@pytest.mark.asyncio
async def test_compute_live_nodes_uses_pdb_not_ca():
    svc = PuppetDBService()
    pdb = [
        {"certname": "ovcompilers.atlc-it.corp.int-x.ai", "deactivated": None},
        {"certname": "ovcompiler1.atlc-it.corp.int-x.ai", "deactivated": None},
        {"certname": "ovca.corp.int-x.ai", "deactivated": None},
        {"certname": "ovdb.corp.int-x.ai", "deactivated": None},
    ]
    excluded = {"ovca.corp.int-x.ai", "ovdb.corp.int-x.ai"}

    with patch.object(svc, "get_nodes", new=AsyncMock(return_value=pdb)):
        with patch(
            "app.services.cluster_config.fleet_excluded_certnames",
            return_value=excluded,
        ):
            live = await svc._compute_live_nodes()

    names = {n["certname"] for n in live}
    assert "ovcompilers.atlc-it.corp.int-x.ai" in names
    assert "ovcompiler1.atlc-it.corp.int-x.ai" in names
    assert "ovca.corp.int-x.ai" not in names
    assert "ovdb.corp.int-x.ai" not in names
