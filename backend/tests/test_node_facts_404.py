"""PuppetDB 404 on per-node facts/resources is empty data, not a 500."""

import asyncio

import httpx

from app.services.puppetdb import PuppetDBService


def _http_404(path: str) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", f"https://puppetdb.example.com{path}")
    resp = httpx.Response(404, request=req, text="Not Found")
    return httpx.HTTPStatusError("404 Not Found", request=req, response=resp)


def _svc() -> PuppetDBService:
    return PuppetDBService.__new__(PuppetDBService)


def test_facts_404_returns_empty_list():
    svc = _svc()
    calls = []

    async def fake_query(endpoint, query=None, params=None):
        calls.append((endpoint, params))
        if endpoint.startswith("nodes/"):
            raise _http_404(f"/pdb/query/v4/{endpoint}")
        return []

    svc._query = fake_query  # type: ignore[method-assign]
    rows = asyncio.run(svc.get_node_facts("web01.example.com"))
    assert rows == []
    assert ("nodes/web01.example.com/facts", None) in calls
    assert ("nodes/web01/facts", None) in calls
    pql = [c for c in calls if c[0] == ""]
    assert pql
    assert 'certname = "web01.example.com"' in (pql[0][1] or {}).get("query", "")


def test_facts_fqdn_404_uses_short_certname():
    svc = _svc()

    async def fake_query(endpoint, query=None, params=None):
        if endpoint == "nodes/locutus1.sjc5.example.com/facts":
            raise _http_404(f"/pdb/query/v4/{endpoint}")
        if endpoint == "nodes/locutus1/facts":
            return [
                {"name": "osfamily", "value": "RedHat", "certname": "locutus1"},
            ]
        raise AssertionError(f"unexpected query {endpoint}")

    svc._query = fake_query  # type: ignore[method-assign]
    rows = asyncio.run(svc.get_node_facts("locutus1.sjc5.example.com"))
    assert rows == [{"name": "osfamily", "value": "RedHat", "certname": "locutus1"}]


def test_facts_pql_fallback_after_rest_404():
    svc = _svc()

    async def fake_query(endpoint, query=None, params=None):
        if endpoint.startswith("nodes/"):
            raise _http_404(f"/pdb/query/v4/{endpoint}")
        q = (params or {}).get("query", "")
        if 'facts { certname = "web01.example.com" }' in q:
            return [{"name": "fqdn", "value": "web01.example.com"}]
        return []

    svc._query = fake_query  # type: ignore[method-assign]
    rows = asyncio.run(svc.get_node_facts("web01.example.com"))
    assert rows == [{"name": "fqdn", "value": "web01.example.com"}]


def test_resources_404_returns_empty_list():
    svc = _svc()

    async def fake_query(endpoint, query=None, params=None):
        if endpoint.startswith("nodes/"):
            raise _http_404(f"/pdb/query/v4/{endpoint}")
        return []

    svc._query = fake_query  # type: ignore[method-assign]
    assert asyncio.run(svc.get_node_resources("web01.example.com")) == []


def test_non_404_still_raises():
    svc = _svc()

    async def fake_query(endpoint, query=None, params=None):
        req = httpx.Request("GET", "https://puppetdb.example.com/pdb/query/v4/nodes/web01/facts")
        resp = httpx.Response(503, request=req, text="unavailable")
        raise httpx.HTTPStatusError("503", request=req, response=resp)

    svc._query = fake_query  # type: ignore[method-assign]
    try:
        asyncio.run(svc.get_node_facts("web01"))
        assert False, "expected HTTPStatusError"
    except httpx.HTTPStatusError as e:
        assert e.response.status_code == 503
