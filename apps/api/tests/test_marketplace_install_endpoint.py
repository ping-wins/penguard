import io
import json
import tarfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.addons.catalog_fetcher import CatalogFetcher
from app.addons.dependencies import (
    get_catalog_fetcher,
    get_connector_registry,
    get_install_service,
    get_loader,
)
from app.addons.install_service import InstallService
from app.addons.installed_store import list_installed
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.dependencies import get_current_api_user, require_admin_user
from app.db import models as _models  # noqa: F401 - register models on Base.metadata
from app.db.base import Base
from app.main import app
from app.routers.marketplace import get_installed_index


def _admin_user() -> dict:
    return {"id": "admin", "roles": ["admin"]}


def _build_tarball(addon_id: str, version: str) -> bytes:
    manifest = {
        "id": addon_id,
        "version": version,
        "name": "Demo",
        "vendor": "Demo",
        "category": "demo",
        "description": "demo",
        "provider": {"type": "demo", "auth": {"kind": "none", "fields": []}},
        "entrypoint": "connector",
    }
    connector = (
        "class _C:\n"
        "    def health_check(self): return {'ok': True}\n"
        "    def get_widget_data(self, req): return {'echo': req}\n"
        "    def ingest_events(self, since): return []\n"
        "    def close(self): pass\n"
        "def get_connector(config):\n"
        "    return _C()\n"
    )

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        root = "fake-root"

        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        add(f"{root}/{addon_id}/{version}/addon.json", json.dumps(manifest).encode())
        add(
            f"{root}/{addon_id}/{version}/connector/__init__.py",
            connector.encode(),
        )
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    tarball = _build_tarball("demo-core", "1.0.0")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents/catalog.json"):
            return httpx.Response(
                200,
                json={
                    "schemaVersion": 1,
                    "addons": [
                        {
                            "id": "demo-core",
                            "name": "Demo Core",
                            "vendor": "Demo",
                            "category": "demo",
                            "icon": None,
                            "description": "...",
                            "latestVersion": "1.0.0",
                            "versions": ["1.0.0"],
                            "tagTemplate": "demo-core-v{version}",
                        }
                    ],
                },
            )
        if "/tarball/demo-core-v1.0.0" in request.url.path:
            return httpx.Response(200, content=tarball)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    loader = AddonLoader()
    registry = ConnectorRegistry()
    catalog = CatalogFetcher(
        repo="ping-wins/penguard-addons", token="t", transport=transport
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def session_factory():
        return Session()

    def installed_index() -> dict[str, dict[str, str]]:
        with session_factory() as session:
            return {
                r.id: {"version": r.version, "installed_at": r.installed_at.isoformat()}
                for r in list_installed(session)
            }

    service = InstallService(
        session_factory=session_factory,
        storage_dir=tmp_path,
        repo="ping-wins/penguard-addons",
        token="t",
        loader=loader,
        transport=transport,
    )

    app.dependency_overrides[get_loader] = lambda: loader
    app.dependency_overrides[get_connector_registry] = lambda: registry
    app.dependency_overrides[get_catalog_fetcher] = lambda: catalog
    app.dependency_overrides[get_install_service] = lambda: service
    app.dependency_overrides[get_installed_index] = installed_index
    app.dependency_overrides[require_admin_user] = _admin_user
    app.dependency_overrides[get_current_api_user] = _admin_user

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_install_then_list_marks_addon_installed(client):
    r = client.post(
        "/api/marketplace/addons/demo-core/install",
        json={"version": "1.0.0"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "installed"

    r2 = client.get("/api/marketplace/addons")
    body = r2.json()
    demo = next(it for it in body["items"] if it["id"] == "demo-core")
    assert demo["installed"] is True
    assert demo["installedVersion"] == "1.0.0"


def test_remote_catalog_items_are_normalized_for_marketplace_ui(client):
    r = client.get("/api/marketplace/addons")
    assert r.status_code == 200, r.text

    demo = next(it for it in r.json()["items"] if it["id"] == "demo-core")
    assert demo["version"] == "1.0.0"
    assert demo["versions"] == ["1.0.0"]
    assert demo["routes"] == []
    assert demo["widgets"] == []
    assert demo["siemEventTypes"] == []
    assert demo["provider"]["auth"]["fields"] == []
    assert demo["installed"] is False


def test_uninstall_clears_installed_flag(client):
    client.post(
        "/api/marketplace/addons/demo-core/install",
        json={"version": "1.0.0"},
    )
    r = client.delete("/api/marketplace/addons/demo-core")
    assert r.status_code == 200, r.text
    body = client.get("/api/marketplace/addons").json()
    demo = next(it for it in body["items"] if it["id"] == "demo-core")
    assert demo["installed"] is False
