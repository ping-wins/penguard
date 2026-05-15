import io
import json
import tarfile
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.addons.contracts import AddonInstallError
from app.addons.install_service import InstallService
from app.addons.installed_store import get_installed
from app.addons.loader import AddonLoader
from app.db import models  # noqa: F401
from app.db.base import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _build_tarball(addon_id: str = "demo-core", version: str = "1.0.0") -> bytes:
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
        "    def get_widget_data(self, req): return {}\n"
        "    def ingest_events(self, since): return []\n"
        "    def close(self): pass\n"
        "def get_connector(config):\n"
        "    return _C()\n"
    )

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        root = "ping-wins-fortidashboard-addons-deadbeef"

        def add_bytes(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        add_bytes(
            f"{root}/{addon_id}/{version}/addon.json",
            json.dumps(manifest).encode(),
        )
        add_bytes(
            f"{root}/{addon_id}/{version}/connector/__init__.py",
            connector.encode(),
        )
    return buf.getvalue()


def _ok_transport(payload: bytes) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/tarball/demo-core-v1.0.0")
        return httpx.Response(200, content=payload)

    return httpx.MockTransport(handler)


def test_install_extracts_and_registers(session, tmp_path):
    tarball = _build_tarball()
    service = InstallService(
        session_factory=lambda: session,
        storage_dir=tmp_path,
        repo="ping-wins/fortidashboard-addons",
        token="t",
        loader=AddonLoader(),
        transport=_ok_transport(tarball),
    )

    factory = service.install("demo-core", version="1.0.0")

    assert callable(factory)
    record = get_installed(session, "demo-core")
    assert record is not None
    assert record.version == "1.0.0"
    assert Path(record.path).is_dir()
    assert (Path(record.path) / "addon.json").is_file()


def test_install_uses_atomic_move_into_storage(session, tmp_path):
    service = InstallService(
        session_factory=lambda: session,
        storage_dir=tmp_path,
        repo="x/y",
        token="t",
        loader=AddonLoader(),
        transport=_ok_transport(_build_tarball()),
    )

    service.install("demo-core", version="1.0.0")

    final = tmp_path / "demo-core" / "1.0.0"
    assert final.is_dir()
    assert not any((tmp_path / ".tmp").iterdir()) if (tmp_path / ".tmp").exists() else True


def test_install_replaces_previous_version(session, tmp_path):
    v1 = _build_tarball(version="1.0.0")
    v2 = _build_tarball(version="1.1.0")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=v1 if calls["n"] == 1 else v2)

    service = InstallService(
        session_factory=lambda: session,
        storage_dir=tmp_path,
        repo="x/y",
        token="t",
        loader=AddonLoader(),
        transport=httpx.MockTransport(handler),
    )
    service.install("demo-core", version="1.0.0")
    service.install("demo-core", version="1.1.0")

    assert get_installed(session, "demo-core").version == "1.1.0"
    assert (tmp_path / "demo-core" / "1.1.0").is_dir()
    trash = list((tmp_path / ".trash").rglob("addon.json"))
    assert any("1.0.0" in str(p) for p in trash)


def test_install_rolls_back_on_invalid_manifest(session, tmp_path):
    def bad_handler(request: httpx.Request) -> httpx.Response:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="root/demo-core/1.0.0/addon.json")
            data = b"not json"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        return httpx.Response(200, content=buf.getvalue())

    service = InstallService(
        session_factory=lambda: session,
        storage_dir=tmp_path,
        repo="x/y",
        token="t",
        loader=AddonLoader(),
        transport=httpx.MockTransport(bad_handler),
    )

    with pytest.raises(AddonInstallError):
        service.install("demo-core", version="1.0.0")

    assert get_installed(session, "demo-core") is None
    assert not (tmp_path / "demo-core").exists()


def test_uninstall_removes_install(session, tmp_path):
    service = InstallService(
        session_factory=lambda: session,
        storage_dir=tmp_path,
        repo="x/y",
        token="t",
        loader=AddonLoader(),
        transport=_ok_transport(_build_tarball()),
    )
    service.install("demo-core", version="1.0.0")

    service.uninstall("demo-core")

    assert get_installed(session, "demo-core") is None
    assert not (tmp_path / "demo-core" / "1.0.0").exists()
