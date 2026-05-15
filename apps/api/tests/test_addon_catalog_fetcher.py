import time

import httpx
import pytest

from app.addons.catalog_fetcher import CatalogFetcher, CatalogFetchError


def _catalog_payload() -> dict:
    return {
        "schemaVersion": 1,
        "addons": [
            {
                "id": "fortigate-core",
                "name": "FortiGate Core",
                "vendor": "Fortinet",
                "category": "firewall",
                "icon": "fortinet",
                "description": "...",
                "latestVersion": "7.6.0",
                "versions": ["7.6.0"],
                "tagTemplate": "fortigate-core-v{version}",
            }
        ],
    }


def _transport(handler):
    return httpx.MockTransport(handler)


def test_fetch_returns_catalog():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/ping-wins/fortidashboard-addons/contents/catalog.json"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["accept"] == "application/vnd.github.raw+json"
        return httpx.Response(200, json=_catalog_payload())

    fetcher = CatalogFetcher(
        repo="ping-wins/fortidashboard-addons",
        token="test-token",
        transport=_transport(handler),
    )

    catalog = fetcher.fetch()
    assert catalog["addons"][0]["id"] == "fortigate-core"


def test_fetch_caches_within_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_catalog_payload())

    fetcher = CatalogFetcher(
        repo="x/y", token="t", transport=_transport(handler), ttl_seconds=60
    )

    fetcher.fetch()
    fetcher.fetch()
    assert calls["n"] == 1


def test_fetch_refreshes_after_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_catalog_payload())

    fetcher = CatalogFetcher(
        repo="x/y", token="t", transport=_transport(handler), ttl_seconds=0
    )
    fetcher.fetch()
    time.sleep(0.01)
    fetcher.fetch()
    assert calls["n"] == 2


def test_invalidate_forces_refetch():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_catalog_payload())

    fetcher = CatalogFetcher(repo="x/y", token="t", transport=_transport(handler))
    fetcher.fetch()
    fetcher.invalidate()
    fetcher.fetch()
    assert calls["n"] == 2


def test_fetch_raises_on_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    fetcher = CatalogFetcher(repo="x/y", token="t", transport=_transport(handler))

    with pytest.raises(CatalogFetchError, match="401"):
        fetcher.fetch()


def test_fetch_raises_on_malformed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    fetcher = CatalogFetcher(repo="x/y", token="t", transport=_transport(handler))

    with pytest.raises(CatalogFetchError):
        fetcher.fetch()
