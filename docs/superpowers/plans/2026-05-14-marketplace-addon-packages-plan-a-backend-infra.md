# Marketplace add-on packages — Plan A: backend infrastructure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend plumbing (loader, install service, connector registry, DB table, endpoints) so an arbitrary add-on package can be downloaded from `ping-wins/penguard-addons`, registered, dynamically imported, and queried via a Protocol-typed connector — verified end-to-end with a synthetic test add-on, without touching FortiGate code yet.

**Architecture:** New `apps/api/app/addons/` modules implement five concerns kept in separate files for clarity: Protocol contracts, dynamic loader (importlib), GitHub catalog fetcher, install service (fetch + extract + validate + atomic move + DB upsert), and a process-wide connector registry. The existing local-dir manifest registry stays untouched — it continues to serve bundled `addons/fortigate/addon.json` while Plan A only adds parallel infrastructure for installed packages. Migration of FortiGate to a package and removal of the local-dir loader is Plan B.

**Tech Stack:** FastAPI, pydantic v2, SQLAlchemy 2.0 + Alembic, httpx (with `MockTransport` for tests), `importlib.util` for dynamic module loading, `tarfile` + `hashlib` for tarball handling, pytest.

---

## Decomposition note

The full design (`docs/superpowers/specs/2026-05-14-marketplace-addon-packages-design.md`) implies three sequential plans:

- **Plan A (this file)** — backend infrastructure, exercised by a synthetic test add-on. Ships independently as "marketplace can install arbitrary packages."
- **Plan B** — extract FortiGate code into the registry repo, tag `fortigate-core-v7.6.0`, wire one-time auto-install on boot, delete monorepo vendor code.
- **Plan C** — frontend install button, progress UI, installed badge in `MarketplacePanel.vue`.

Plan B and C depend on A being merged and green. They do not depend on each other.

---

## File structure (Plan A)

### New files

| Path | Responsibility |
|------|----------------|
| `apps/api/app/addons/contracts.py` | `AddonConnector` Protocol + dashboard-side DTOs (`HealthCheckResult`, `WidgetDataRequest`, `SiemEvent`) + typed errors (`AddonLoadError`, `AddonInstallError`). |
| `apps/api/app/addons/installed_store.py` | SQLAlchemy model `InstalledAddon` + repository functions (`list_all`, `get`, `upsert`, `delete`). |
| `apps/api/app/addons/loader.py` | `AddonLoader.load(install) -> get_connector` and `unload(addon_id)` using `importlib.util`. |
| `apps/api/app/addons/catalog_fetcher.py` | `CatalogFetcher.fetch()` — GitHub API call for `catalog.json` with 5-minute TTL cache, configurable `httpx.BaseTransport` for tests. |
| `apps/api/app/addons/install_service.py` | `InstallService.install(addon_id, version)` and `uninstall(addon_id)`. Streams tarball, sha256, extracts to staging, validates, atomic-moves, upserts row, calls loader. |
| `apps/api/app/addons/registry_runtime.py` | `ConnectorRegistry` singleton: `register`, `unregister`, `get(addon_id, integration_id, config)` with per-pair instance cache. |
| `apps/api/migrations/versions/20260514_0011_create_installed_addons.py` | Alembic migration. |
| `apps/api/tests/test_addon_loader.py` | Loader unit tests (tmpdir fake addon). |
| `apps/api/tests/test_addon_catalog_fetcher.py` | Catalog fetcher tests with `httpx.MockTransport`. |
| `apps/api/tests/test_addon_install_service.py` | Install service tests including failure rollback. |
| `apps/api/tests/test_addon_registry_runtime.py` | Connector registry tests. |
| `apps/api/tests/test_marketplace_install_endpoint.py` | End-to-end integration test through the FastAPI app. |
| `apps/api/tests/fixtures/fake_addon/__init__.py` | Static fixture: minimal `connector/__init__.py` for tarball assembly. |

### Modified files

| Path | Change |
|------|--------|
| `apps/api/app/addons/manifest.py` | Add optional `entrypoint` (default `"connector"`) and `requirements: list[str]` fields. |
| `apps/api/app/routers/marketplace.py` | Add `POST /addons/{id}/install`, `DELETE /addons/{id}`. Update `GET /addons` to merge installed state. |
| `apps/api/app/main.py` | On startup, call `InstallService.bootstrap_installed()` to load all installed packages. |
| `apps/api/app/core/config.py` | Add `marketplace_gh_token: str | None`, `marketplace_registry_repo: str` (default `ping-wins/penguard-addons`), `addons_storage_dir: Path` (default `/app/data/addons`). |
| `docker-compose.yml` | Add named volume `addons_data` mounted at `/app/data/addons`; pass `MARKETPLACE_GH_TOKEN` env to `api`. |

---

## Task 1: Extend manifest schema with `entrypoint` and `requirements`

**Files:**
- Modify: `apps/api/app/addons/manifest.py`
- Test: `apps/api/tests/test_addon_manifest_schema.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_addon_manifest_schema.py`:

```python
from app.addons.manifest import AddonManifest


def _base_payload() -> dict:
    return {
        "id": "demo",
        "version": "1.0.0",
        "name": "Demo",
        "vendor": "Demo Inc",
        "category": "demo",
        "description": "demo",
        "provider": {"type": "demo", "auth": {"kind": "none", "fields": []}},
    }


def test_manifest_defaults_when_entrypoint_and_requirements_absent():
    m = AddonManifest.model_validate(_base_payload())
    assert m.entrypoint == "connector"
    assert m.requirements == []


def test_manifest_accepts_explicit_entrypoint_and_requirements():
    payload = _base_payload()
    payload["entrypoint"] = "src"
    payload["requirements"] = ["httpx>=0.27,<1.0", "pydantic>=2"]
    m = AddonManifest.model_validate(payload)
    assert m.entrypoint == "src"
    assert m.requirements == ["httpx>=0.27,<1.0", "pydantic>=2"]


def test_manifest_dump_round_trips_new_fields():
    payload = _base_payload()
    payload["entrypoint"] = "src"
    payload["requirements"] = ["httpx"]
    dumped = AddonManifest.model_validate(payload).model_dump(by_alias=True)
    assert dumped["entrypoint"] == "src"
    assert dumped["requirements"] == ["httpx"]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_addon_manifest_schema.py -v
```

Expected: 3 failures — `AttributeError: 'AddonManifest' object has no attribute 'entrypoint'`.

- [ ] **Step 3: Add the fields to the schema**

Edit `apps/api/app/addons/manifest.py`. After the existing `siem_event_types` line in `AddonManifest`, add:

```python
    entrypoint: str = "connector"
    requirements: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_addon_manifest_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/addons/manifest.py apps/api/tests/test_addon_manifest_schema.py
git commit -m "feat(addons): manifest fields for entrypoint and requirements"
```

---

## Task 2: Alembic migration for `installed_addons` table

**Files:**
- Create: `apps/api/migrations/versions/20260514_0011_create_installed_addons.py`

Current head revision is `20260513_0010` (file `20260513_0010_fortigate_ingestion_status.py`). The new migration must follow the project's revision-id convention (`YYYYMMDD_NNNN`).

- [ ] **Step 1: Create the migration file**

Create `apps/api/migrations/versions/20260514_0011_create_installed_addons.py`:

```python
"""create installed_addons

Revision ID: 20260514_0011
Revises: 20260513_0010
Create Date: 2026-05-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0011"
down_revision: str | None = "20260513_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installed_addons",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("installed_addons")
```

- [ ] **Step 2: Run the migration**

```bash
docker compose exec -T api uv run alembic upgrade head
```

Expected output ends with `Running upgrade 20260513_0010 -> 20260514_0011, create installed_addons`.

- [ ] **Step 3: Verify the table exists**

```bash
docker compose exec -T db psql -U penguard -d penguard -c "\d installed_addons"
```

Expected: table description with all 7 columns and `id` as primary key.

- [ ] **Step 4: Commit**

```bash
git add apps/api/migrations/versions/20260514_0011_create_installed_addons.py
git commit -m "feat(addons): migration for installed_addons table"
```

---

## Task 3: `installed_store.py` SQLAlchemy model + repository

**Files:**
- Create: `apps/api/app/addons/installed_store.py`
- Modify: `apps/api/app/db/models.py` (register the new model so Alembic and `Base.metadata` see it)
- Test: `apps/api/tests/test_installed_store.py`

Confirmed conventions: `Base = sqlalchemy.orm.DeclarativeBase` lives in `apps/api/app/db/base.py`. All models are defined in `apps/api/app/db/models.py` and imported by `migrations/env.py` via `from app.db import models  # noqa: F401`. The new model lives in `app/addons/installed_store.py`; we add a re-export in `app.db.models` so the env import path still finds it.

- [ ] **Step 2: Write the failing test**

Create `apps/api/tests/test_installed_store.py`:

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.addons.installed_store import (
    InstalledAddonRecord,
    delete_installed,
    get_installed,
    list_installed,
    upsert_installed,
)
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


def _record() -> InstalledAddonRecord:
    return InstalledAddonRecord(
        id="demo-core",
        version="1.0.0",
        path="/app/data/addons/demo-core/1.0.0",
        tag="demo-core-v1.0.0",
        sha256="a" * 64,
        status="active",
        installed_at=datetime.now(UTC),
    )


def test_upsert_inserts_new_row(session):
    upsert_installed(session, _record())
    assert get_installed(session, "demo-core").version == "1.0.0"


def test_upsert_replaces_existing(session):
    upsert_installed(session, _record())
    second = _record()
    second.version = "1.1.0"
    second.path = "/app/data/addons/demo-core/1.1.0"
    second.tag = "demo-core-v1.1.0"
    upsert_installed(session, second)

    got = get_installed(session, "demo-core")
    assert got.version == "1.1.0"
    assert got.path.endswith("1.1.0")


def test_list_returns_all(session):
    upsert_installed(session, _record())
    second = _record()
    second.id = "other"
    upsert_installed(session, second)
    ids = {r.id for r in list_installed(session)}
    assert ids == {"demo-core", "other"}


def test_delete_removes_row(session):
    upsert_installed(session, _record())
    delete_installed(session, "demo-core")
    assert get_installed(session, "demo-core") is None
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_installed_store.py -v
```

Expected: ImportError — `app.addons.installed_store` does not exist.

- [ ] **Step 4: Implement the store**

Create `apps/api/app/addons/installed_store.py`:

```python
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, DateTime, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class InstalledAddonModel(Base):
    __tablename__ = "installed_addons"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass
class InstalledAddonRecord:
    id: str
    version: str
    path: str
    tag: str
    sha256: str
    status: str
    installed_at: datetime


def _to_record(model: InstalledAddonModel) -> InstalledAddonRecord:
    return InstalledAddonRecord(
        id=model.id,
        version=model.version,
        path=model.path,
        tag=model.tag,
        sha256=model.sha256,
        status=model.status,
        installed_at=model.installed_at,
    )


def upsert_installed(session: Session, record: InstalledAddonRecord) -> None:
    existing = session.get(InstalledAddonModel, record.id)
    if existing is None:
        session.add(
            InstalledAddonModel(
                id=record.id,
                version=record.version,
                path=record.path,
                tag=record.tag,
                sha256=record.sha256,
                status=record.status,
                installed_at=record.installed_at,
            )
        )
    else:
        existing.version = record.version
        existing.path = record.path
        existing.tag = record.tag
        existing.sha256 = record.sha256
        existing.status = record.status
        existing.installed_at = record.installed_at
    session.commit()


def get_installed(session: Session, addon_id: str) -> InstalledAddonRecord | None:
    model = session.get(InstalledAddonModel, addon_id)
    return _to_record(model) if model else None


def list_installed(session: Session) -> list[InstalledAddonRecord]:
    rows = session.execute(select(InstalledAddonModel)).scalars().all()
    return [_to_record(row) for row in rows]


def delete_installed(session: Session, addon_id: str) -> None:
    model = session.get(InstalledAddonModel, addon_id)
    if model is not None:
        session.delete(model)
        session.commit()
```

- [ ] **Step 5: Register the model with `app.db.models`**

Append to `apps/api/app/db/models.py` (at the end of the file):

```python
from app.addons.installed_store import InstalledAddonModel  # noqa: F401
```

This guarantees `Base.metadata` sees the new model when Alembic and tests import `app.db.models`.

- [ ] **Step 6: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_installed_store.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/addons/installed_store.py apps/api/app/db/models.py apps/api/tests/test_installed_store.py
git commit -m "feat(addons): installed_addons SQLAlchemy model and repository"
```

---

## Task 4: Protocol contracts module

**Files:**
- Create: `apps/api/app/addons/contracts.py`
- Test: none (Protocols are exercised in loader tests)

- [ ] **Step 1: Create the contracts module**

Create `apps/api/app/addons/contracts.py`:

```python
"""Contracts that bound the dashboard <-> add-on package interface.

Add-on packages do NOT import this module — the `AddonConnector` Protocol
is duck-typed. Anything in the dashboard that calls an add-on imports
from here.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class AddonError(RuntimeError):
    """Base for errors raised by the add-on subsystem."""


class AddonLoadError(AddonError):
    """Raised when loader cannot import or register an installed package."""


class AddonInstallError(AddonError):
    """Raised when install service cannot fetch / extract / validate a package."""


@dataclass
class HealthCheckResult:
    ok: bool
    status: str
    device: dict[str, Any]
    message: str | None = None
    latency_ms: int | None = None


@dataclass
class WidgetDataRequest:
    widget_id: str
    integration_id: str
    config: dict[str, Any]
    since: datetime | None = None


@dataclass
class SiemEvent:
    event_type: str
    occurred_at: datetime
    severity: str
    payload: dict[str, Any]


class AddonConnector(Protocol):
    def health_check(self) -> dict[str, Any]: ...
    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]: ...
    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
docker compose exec -T api uv run python -c "from app.addons.contracts import AddonConnector, HealthCheckResult, AddonLoadError, AddonInstallError; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/addons/contracts.py
git commit -m "feat(addons): Protocol contracts and typed errors"
```

---

## Task 5: `AddonLoader` with importlib isolation

**Files:**
- Create: `apps/api/app/addons/loader.py`
- Create: `apps/api/tests/test_addon_loader.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_addon_loader.py`:

```python
import json
import sys
from pathlib import Path

import pytest

from app.addons.contracts import AddonLoadError
from app.addons.installed_store import InstalledAddonRecord
from app.addons.loader import AddonLoader


def _write_addon(root: Path, addon_id: str = "demo-core", version: str = "1.0.0") -> Path:
    addon_dir = root / addon_id / version
    connector_dir = addon_dir / "connector"
    connector_dir.mkdir(parents=True)

    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": addon_id,
                "version": version,
                "name": "Demo",
                "vendor": "Demo",
                "category": "demo",
                "description": "demo",
                "provider": {"type": "demo", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "connector",
            }
        )
    )
    (connector_dir / "__init__.py").write_text(
        "class _C:\n"
        "    def health_check(self): return {'ok': True}\n"
        "    def get_widget_data(self, req): return {'data': req}\n"
        "    def ingest_events(self, since): return []\n"
        "    def close(self): pass\n"
        "def get_connector(config):\n"
        "    return _C()\n"
    )
    return addon_dir


def _record(path: Path, addon_id: str = "demo-core", version: str = "1.0.0") -> InstalledAddonRecord:
    from datetime import UTC, datetime

    return InstalledAddonRecord(
        id=addon_id,
        version=version,
        path=str(path),
        tag=f"{addon_id}-v{version}",
        sha256="a" * 64,
        status="active",
        installed_at=datetime.now(UTC),
    )


def test_loader_returns_get_connector_factory(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()

    factory = loader.load(_record(addon_dir))

    connector = factory({})
    assert connector.health_check() == {"ok": True}


def test_loader_uses_namespaced_module(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()

    loader.load(_record(addon_dir))

    assert "penguard_addons.demo-core" in sys.modules


def test_loader_unload_clears_sys_modules(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()
    loader.load(_record(addon_dir))

    loader.unload("demo-core")

    assert "penguard_addons.demo-core" not in sys.modules


def test_loader_rejects_missing_entrypoint(tmp_path):
    addon_dir = tmp_path / "broken" / "1.0.0"
    addon_dir.mkdir(parents=True)
    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": "broken",
                "version": "1.0.0",
                "name": "Broken",
                "vendor": "x",
                "category": "x",
                "description": "x",
                "provider": {"type": "x", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "connector",
            }
        )
    )

    with pytest.raises(AddonLoadError, match="entrypoint"):
        AddonLoader().load(_record(addon_dir, addon_id="broken"))


def test_loader_rejects_missing_get_connector(tmp_path):
    addon_dir = _write_addon(tmp_path, addon_id="no-factory")
    (addon_dir / "connector" / "__init__.py").write_text("# no get_connector\n")

    with pytest.raises(AddonLoadError, match="get_connector"):
        AddonLoader().load(_record(addon_dir, addon_id="no-factory"))


def test_loader_rejects_path_traversal_entrypoint(tmp_path):
    addon_dir = tmp_path / "traverse" / "1.0.0"
    (addon_dir / "connector").mkdir(parents=True)
    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": "traverse",
                "version": "1.0.0",
                "name": "x",
                "vendor": "x",
                "category": "x",
                "description": "x",
                "provider": {"type": "x", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "../../etc",
            }
        )
    )

    with pytest.raises(AddonLoadError, match="entrypoint"):
        AddonLoader().load(_record(addon_dir, addon_id="traverse"))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_addon_loader.py -v
```

Expected: ImportError for `app.addons.loader`.

- [ ] **Step 3: Implement the loader**

Create `apps/api/app/addons/loader.py`:

```python
"""Dynamic loader for installed add-on packages.

Each add-on is imported as `penguard_addons.<id>` via
`importlib.util.spec_from_file_location` to keep it off the global
`sys.path`. Submodule lookup is scoped to the package directory.
"""

import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

from app.addons.contracts import AddonConnector, AddonLoadError
from app.addons.installed_store import InstalledAddonRecord
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)

_MODULE_NAMESPACE = "penguard_addons"


class AddonLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, ModuleType] = {}

    def load(self, install: InstalledAddonRecord) -> Callable[[dict], AddonConnector]:
        addon_root = Path(install.path).resolve()
        manifest_path = addon_root / "addon.json"
        if not manifest_path.is_file():
            raise AddonLoadError(f"addon manifest missing at {manifest_path}")

        manifest = AddonManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
        entry_dir = (addon_root / manifest.entrypoint).resolve()

        try:
            entry_dir.relative_to(addon_root)
        except ValueError as exc:
            raise AddonLoadError(
                f"entrypoint '{manifest.entrypoint}' escapes package root"
            ) from exc

        if not entry_dir.is_dir():
            raise AddonLoadError(f"entrypoint directory not found: {entry_dir}")

        entry = entry_dir / "__init__.py"
        if not entry.is_file():
            raise AddonLoadError(f"entrypoint package has no __init__.py: {entry}")

        module_name = f"{_MODULE_NAMESPACE}.{install.id}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            entry,
            submodule_search_locations=[str(entry_dir)],
        )
        if spec is None or spec.loader is None:
            raise AddonLoadError(f"failed to build import spec for {install.id}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise AddonLoadError(f"failed to import add-on {install.id}: {exc}") from exc

        factory = getattr(module, "get_connector", None)
        if not callable(factory):
            sys.modules.pop(module_name, None)
            raise AddonLoadError(f"add-on {install.id} missing get_connector(config)")

        self._loaded[install.id] = module
        logger.info("addon_loaded id=%s version=%s", install.id, install.version)
        return factory

    def unload(self, addon_id: str) -> None:
        module = self._loaded.pop(addon_id, None)
        if module is not None:
            sys.modules.pop(module.__name__, None)
            logger.info("addon_unloaded id=%s", addon_id)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_addon_loader.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/addons/loader.py apps/api/tests/test_addon_loader.py
git commit -m "feat(addons): importlib-isolated dynamic loader"
```

---

## Task 6: `CatalogFetcher` with TTL cache

**Files:**
- Create: `apps/api/app/addons/catalog_fetcher.py`
- Create: `apps/api/tests/test_addon_catalog_fetcher.py`
- Modify: `apps/api/app/core/config.py`

- [ ] **Step 1: Add config fields**

Open `apps/api/app/core/config.py` and locate the `Settings` class. Add (preserve existing fields):

```python
    marketplace_gh_token: str | None = None
    marketplace_registry_repo: str = "ping-wins/penguard-addons"
    addons_storage_dir: Path = Path("/app/data/addons")
```

If `Path` is not imported there, add `from pathlib import Path` at the top.

- [ ] **Step 2: Write the failing test**

Create `apps/api/tests/test_addon_catalog_fetcher.py`:

```python
import json
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
        assert request.url.path == "/repos/ping-wins/penguard-addons/contents/catalog.json"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["accept"] == "application/vnd.github.raw+json"
        return httpx.Response(200, json=_catalog_payload())

    fetcher = CatalogFetcher(
        repo="ping-wins/penguard-addons",
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
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_addon_catalog_fetcher.py -v
```

Expected: ImportError for `app.addons.catalog_fetcher`.

- [ ] **Step 4: Implement the fetcher**

Create `apps/api/app/addons/catalog_fetcher.py`:

```python
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CatalogFetchError(RuntimeError):
    pass


class CatalogFetcher:
    def __init__(
        self,
        *,
        repo: str,
        token: str | None,
        transport: httpx.BaseTransport | None = None,
        ttl_seconds: float = 300.0,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._repo = repo
        self._token = token
        self._transport = transport
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._cached: dict[str, Any] | None = None
        self._cached_at: float = 0.0

    def fetch(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._cached is not None and (now - self._cached_at) <= self._ttl:
            return self._cached

        url = f"https://api.github.com/repos/{self._repo}/contents/catalog.json"
        headers = {"Accept": "application/vnd.github.raw+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise CatalogFetchError(f"catalog request failed: {exc}") from exc

        if response.status_code != 200:
            raise CatalogFetchError(
                f"catalog fetch returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise CatalogFetchError("catalog response was not valid JSON") from exc

        if not isinstance(payload, dict) or "addons" not in payload:
            raise CatalogFetchError("catalog payload missing 'addons' key")

        self._cached = payload
        self._cached_at = now
        logger.info("catalog_fetched repo=%s addons=%s", self._repo, len(payload["addons"]))
        return payload

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_addon_catalog_fetcher.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/addons/catalog_fetcher.py apps/api/tests/test_addon_catalog_fetcher.py apps/api/app/core/config.py
git commit -m "feat(addons): GitHub catalog fetcher with TTL cache"
```

---

## Task 7: `InstallService` — fetch, extract, validate, register

**Files:**
- Create: `apps/api/app/addons/install_service.py`
- Create: `apps/api/tests/test_addon_install_service.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_addon_install_service.py`:

```python
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.addons.contracts import AddonInstallError
from app.addons.install_service import InstallService
from app.addons.installed_store import get_installed, list_installed
from app.addons.loader import AddonLoader
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
    """Build a tarball with the top-level dir GitHub adds, then <id>/<version>/..."""
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
        # Simulate GitHub's top-level dir like "ping-wins-penguard-addons-abc1234/"
        root = "ping-wins-penguard-addons-deadbeef"

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
        repo="ping-wins/penguard-addons",
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_addon_install_service.py -v
```

Expected: ImportError for `app.addons.install_service`.

- [ ] **Step 3: Implement the install service**

Create `apps/api/app/addons/install_service.py`:

```python
import hashlib
import io
import json
import logging
import shutil
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import httpx

from app.addons.contracts import AddonConnector, AddonInstallError
from app.addons.installed_store import (
    InstalledAddonRecord,
    delete_installed,
    get_installed,
    upsert_installed,
)
from app.addons.loader import AddonLoader
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)


class InstallService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], object],
        storage_dir: Path,
        repo: str,
        token: str | None,
        loader: AddonLoader,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._storage = Path(storage_dir)
        self._repo = repo
        self._token = token
        self._loader = loader
        self._transport = transport
        self._timeout = timeout_seconds

    # ----- public -----

    def install(
        self, addon_id: str, *, version: str
    ) -> Callable[[dict], AddonConnector]:
        tag = f"{addon_id}-v{version}"
        tarball = self._fetch_tarball(tag)
        sha = hashlib.sha256(tarball).hexdigest()

        staging = self._storage / ".tmp" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=True)
        try:
            self._extract(tarball, staging)
            source = self._locate_package(staging, addon_id, version)
            self._validate_manifest(source, addon_id, version)

            target = self._storage / addon_id / version
            self._move_into_place(source, target)

            record = InstalledAddonRecord(
                id=addon_id,
                version=version,
                path=str(target),
                tag=tag,
                sha256=sha,
                status="active",
                installed_at=datetime.now(UTC),
            )
            self._write_install_metadata(target, record)

            session = self._session_factory()
            upsert_installed(session, record)

            factory = self._loader.load(record)
            logger.info("addon_installed id=%s version=%s tag=%s", addon_id, version, tag)
            return factory
        except AddonInstallError:
            raise
        except Exception as exc:
            raise AddonInstallError(f"install failed for {addon_id}@{version}: {exc}") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def uninstall(self, addon_id: str) -> None:
        session = self._session_factory()
        record = get_installed(session, addon_id)
        if record is None:
            raise AddonInstallError(f"add-on not installed: {addon_id}")

        path = Path(record.path)
        if path.is_dir():
            trash = self._storage / ".trash" / addon_id / f"{record.version}-{int(datetime.now(UTC).timestamp())}"
            trash.parent.mkdir(parents=True, exist_ok=True)
            path.rename(trash)

        delete_installed(session, addon_id)
        self._loader.unload(addon_id)
        logger.info("addon_uninstalled id=%s", addon_id)

    # ----- internals -----

    def _fetch_tarball(self, tag: str) -> bytes:
        url = f"https://api.github.com/repos/{self._repo}/tarball/{tag}"
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise AddonInstallError(f"tarball request failed: {exc}") from exc

        if response.status_code != 200:
            raise AddonInstallError(
                f"tarball fetch returned HTTP {response.status_code}"
            )

        return response.content

    def _extract(self, payload: bytes, dest: Path) -> None:
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
                for member in tar.getmembers():
                    name = member.name
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise AddonInstallError(f"unsafe tarball member: {name}")
                tar.extractall(dest)
        except tarfile.TarError as exc:
            raise AddonInstallError(f"invalid tarball: {exc}") from exc

    def _locate_package(self, staging: Path, addon_id: str, version: str) -> Path:
        candidates = list(staging.iterdir())
        if len(candidates) != 1 or not candidates[0].is_dir():
            raise AddonInstallError(
                "tarball top-level layout unexpected: need exactly one root directory"
            )
        root = candidates[0]
        package = root / addon_id / version
        if not package.is_dir():
            raise AddonInstallError(
                f"package not found at expected path {addon_id}/{version} inside tarball"
            )
        return package

    def _validate_manifest(self, package: Path, addon_id: str, version: str) -> None:
        manifest_path = package / "addon.json"
        if not manifest_path.is_file():
            raise AddonInstallError("addon.json missing from package")

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AddonInstallError(f"addon.json is not valid JSON: {exc}") from exc

        try:
            manifest = AddonManifest.model_validate(payload)
        except Exception as exc:
            raise AddonInstallError(f"addon.json failed schema validation: {exc}") from exc

        if manifest.id != addon_id:
            raise AddonInstallError(
                f"manifest id '{manifest.id}' does not match requested '{addon_id}'"
            )
        if manifest.version != version:
            raise AddonInstallError(
                f"manifest version '{manifest.version}' does not match requested '{version}'"
            )

        entry = (package / manifest.entrypoint).resolve()
        try:
            entry.relative_to(package.resolve())
        except ValueError as exc:
            raise AddonInstallError(
                f"entrypoint '{manifest.entrypoint}' escapes package root"
            ) from exc
        if not entry.is_dir() or not (entry / "__init__.py").is_file():
            raise AddonInstallError(
                f"entrypoint '{manifest.entrypoint}' is not a Python package"
            )

    def _move_into_place(self, source: Path, target: Path) -> None:
        if target.exists():
            ts = int(datetime.now(UTC).timestamp())
            trash = self._storage / ".trash" / target.parent.name / f"{target.name}-{ts}"
            trash.parent.mkdir(parents=True, exist_ok=True)
            target.rename(trash)

        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)

    def _write_install_metadata(self, target: Path, record: InstalledAddonRecord) -> None:
        (target / ".install.json").write_text(
            json.dumps(
                {
                    "id": record.id,
                    "version": record.version,
                    "tag": record.tag,
                    "sha256": record.sha256,
                    "installed_at": record.installed_at.isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_addon_install_service.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/addons/install_service.py apps/api/tests/test_addon_install_service.py
git commit -m "feat(addons): install service (fetch, validate, atomic move)"
```

---

## Task 8: `ConnectorRegistry` runtime

**Files:**
- Create: `apps/api/app/addons/registry_runtime.py`
- Create: `apps/api/tests/test_addon_registry_runtime.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_addon_registry_runtime.py`:

```python
import pytest

from app.addons.contracts import AddonError
from app.addons.registry_runtime import ConnectorRegistry


class _FakeConnector:
    def __init__(self, config):
        self.config = config

    def health_check(self):
        return {"ok": True, "config": self.config}

    def get_widget_data(self, req):
        return {}

    def ingest_events(self, since):
        return []

    def close(self):
        return None


def _factory(config):
    return _FakeConnector(config)


def test_register_and_get_instance_per_pair():
    reg = ConnectorRegistry()
    reg.register("demo", _factory)

    a = reg.get("demo", integration_id="i1", config={"a": 1})
    b = reg.get("demo", integration_id="i1", config={"a": 1})
    c = reg.get("demo", integration_id="i2", config={"a": 2})

    assert a is b
    assert a is not c
    assert c.config == {"a": 2}


def test_unregister_removes_factory_and_closes_instances():
    reg = ConnectorRegistry()
    reg.register("demo", _factory)
    instance = reg.get("demo", integration_id="i1", config={})

    reg.unregister("demo")

    with pytest.raises(AddonError, match="demo"):
        reg.get("demo", integration_id="i1", config={})


def test_get_unknown_addon_raises():
    reg = ConnectorRegistry()
    with pytest.raises(AddonError, match="not registered"):
        reg.get("missing", integration_id="x", config={})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker compose exec -T api uv run pytest tests/test_addon_registry_runtime.py -v
```

Expected: ImportError for `app.addons.registry_runtime`.

- [ ] **Step 3: Implement the registry**

Create `apps/api/app/addons/registry_runtime.py`:

```python
import logging
from typing import Callable

from app.addons.contracts import AddonConnector, AddonError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[dict], AddonConnector]] = {}
        self._instances: dict[tuple[str, str], AddonConnector] = {}

    def register(self, addon_id: str, factory: Callable[[dict], AddonConnector]) -> None:
        self._factories[addon_id] = factory
        logger.info("connector_registered addon_id=%s", addon_id)

    def unregister(self, addon_id: str) -> None:
        self._factories.pop(addon_id, None)
        for key in list(self._instances.keys()):
            if key[0] == addon_id:
                instance = self._instances.pop(key)
                try:
                    instance.close()
                except Exception as exc:
                    logger.warning("connector_close_failed addon_id=%s err=%s", addon_id, exc)
        logger.info("connector_unregistered addon_id=%s", addon_id)

    def get(
        self, addon_id: str, *, integration_id: str, config: dict
    ) -> AddonConnector:
        factory = self._factories.get(addon_id)
        if factory is None:
            raise AddonError(f"connector not registered: {addon_id}")

        key = (addon_id, integration_id)
        if key not in self._instances:
            self._instances[key] = factory(config)
        return self._instances[key]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker compose exec -T api uv run pytest tests/test_addon_registry_runtime.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/addons/registry_runtime.py apps/api/tests/test_addon_registry_runtime.py
git commit -m "feat(addons): connector registry runtime"
```

---

## Task 9: Wire install/uninstall endpoints into the router

**Files:**
- Modify: `apps/api/app/routers/marketplace.py`
- Modify: `apps/api/app/main.py` (DI wiring)
- Create: `apps/api/app/addons/dependencies.py`

- [ ] **Step 1: Centralize DI for the new services**

Create `apps/api/app/addons/dependencies.py`:

```python
from functools import lru_cache

from app.addons.catalog_fetcher import CatalogFetcher
from app.addons.install_service import InstallService
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry
from app.core.config import get_settings
from app.db.session import SessionLocal


@lru_cache(maxsize=1)
def get_loader() -> AddonLoader:
    return AddonLoader()


@lru_cache(maxsize=1)
def get_connector_registry() -> ConnectorRegistry:
    return ConnectorRegistry()


@lru_cache(maxsize=1)
def get_catalog_fetcher() -> CatalogFetcher:
    settings = get_settings()
    return CatalogFetcher(
        repo=settings.marketplace_registry_repo,
        token=settings.marketplace_gh_token,
    )


@lru_cache(maxsize=1)
def get_install_service() -> InstallService:
    settings = get_settings()
    return InstallService(
        session_factory=lambda: SessionLocal(),
        storage_dir=settings.addons_storage_dir,
        repo=settings.marketplace_registry_repo,
        token=settings.marketplace_gh_token,
        loader=get_loader(),
    )
```

If `app.db.session.SessionLocal` does not exist, find the project's session factory (search `sessionmaker` under `apps/api/app/`) and adjust the import.

- [ ] **Step 2: Replace the marketplace router**

Open `apps/api/app/routers/marketplace.py`. Replace its contents with:

```python
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.addons.catalog_fetcher import CatalogFetcher, CatalogFetchError
from app.addons.contracts import AddonError, AddonInstallError, AddonLoadError
from app.addons.dependencies import (
    get_catalog_fetcher,
    get_connector_registry,
    get_install_service,
)
from app.addons.install_service import InstallService
from app.addons.installed_store import get_installed, list_installed
from app.addons.registry import get_addon, list_addons, reload_addons
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.dependencies import get_current_api_user, require_admin_user
from app.db.session import SessionLocal

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _bundled_items() -> list[dict[str, Any]]:
    return [m.model_dump(by_alias=True) for m in list_addons()]


def _installed_index() -> dict[str, dict[str, Any]]:
    with SessionLocal() as session:
        return {
            r.id: {"version": r.version, "installed_at": r.installed_at.isoformat()}
            for r in list_installed(session)
        }


@router.get("/addons")
def list_marketplace_addons(
    _user: Annotated[dict, Depends(get_current_api_user)],
    catalog: Annotated[CatalogFetcher, Depends(get_catalog_fetcher)],
) -> dict:
    installed = _installed_index()
    bundled = _bundled_items()

    remote_items: list[dict[str, Any]] = []
    catalog_error: str | None = None
    try:
        remote_items = catalog.fetch().get("addons", [])
    except CatalogFetchError as exc:
        catalog_error = str(exc)

    by_id: dict[str, dict[str, Any]] = {}
    for entry in bundled:
        by_id[entry["id"]] = {**entry, "source": "bundled"}
    for entry in remote_items:
        merged = {**by_id.get(entry["id"], {}), **entry, "source": "remote"}
        by_id[entry["id"]] = merged

    items: list[dict[str, Any]] = []
    for entry in by_id.values():
        info = installed.get(entry["id"])
        items.append(
            {
                **entry,
                "installed": info is not None,
                "installedVersion": info["version"] if info else None,
            }
        )
    return {"items": items, "count": len(items), "catalogError": catalog_error}


@router.get("/addons/{addon_id}")
def get_marketplace_addon(
    addon_id: str,
    _user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    manifest = get_addon(addon_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Add-on not found")
    return manifest.model_dump(by_alias=True)


@router.post("/addons/refresh")
def refresh_marketplace_addons(
    _admin: Annotated[dict, Depends(require_admin_user)],
    catalog: Annotated[CatalogFetcher, Depends(get_catalog_fetcher)],
) -> dict:
    catalog.invalidate()
    return {"reloaded": len(reload_addons())}


@router.post("/addons/{addon_id}/install")
def install_marketplace_addon(
    addon_id: str,
    _admin: Annotated[dict, Depends(require_admin_user)],
    service: Annotated[InstallService, Depends(get_install_service)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    body: dict = Body(...),
) -> dict:
    version = body.get("version")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")
    try:
        factory = service.install(addon_id, version=version)
    except AddonInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AddonLoadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    registry.register(addon_id, factory)
    return {"id": addon_id, "version": version, "status": "installed"}


@router.delete("/addons/{addon_id}")
def uninstall_marketplace_addon(
    addon_id: str,
    _admin: Annotated[dict, Depends(require_admin_user)],
    service: Annotated[InstallService, Depends(get_install_service)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> dict:
    try:
        service.uninstall(addon_id)
    except AddonInstallError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    registry.unregister(addon_id)
    return {"id": addon_id, "status": "uninstalled"}
```

- [ ] **Step 3: Rebuild the API and probe endpoints exist**

```bash
docker compose up -d --build api
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/marketplace/addons/x/install -H "content-type: application/json" -d '{"version":"1.0.0"}'
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://localhost:8000/api/marketplace/addons/x
```

Expected: `401` for both (auth required) — route exists.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/addons/dependencies.py apps/api/app/routers/marketplace.py
git commit -m "feat(addons): install/uninstall endpoints + catalog merge in list"
```

---

## Task 10: Boot bootstrap — load installed add-ons on startup

**Files:**
- Modify: `apps/api/app/main.py` (existing `lifespan` async context manager)
- Create: `apps/api/app/addons/bootstrap.py`

`apps/api/app/main.py` already uses an `asynccontextmanager` lifespan (it boots a FortiGate ingestion scheduler). Extend that same lifespan, do not introduce a separate `@app.on_event("startup")` decorator.

- [ ] **Step 1: Implement the bootstrap routine**

Create `apps/api/app/addons/bootstrap.py`:

```python
import logging

from sqlalchemy.orm import Session

from app.addons.installed_store import list_installed
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry

logger = logging.getLogger(__name__)


def bootstrap_installed_addons(
    *, session: Session, loader: AddonLoader, registry: ConnectorRegistry
) -> None:
    records = list_installed(session)
    for record in records:
        try:
            factory = loader.load(record)
        except Exception as exc:
            logger.exception(
                "addon_bootstrap_failed id=%s version=%s err=%s",
                record.id,
                record.version,
                exc,
            )
            continue
        registry.register(record.id, factory)
    logger.info("addon_bootstrap_loaded count=%s", len(records))
```

- [ ] **Step 2: Wire the bootstrap into the existing lifespan**

Open `apps/api/app/main.py`. At the top of the file, add imports next to the other `from app.*` imports:

```python
from app.addons.bootstrap import bootstrap_installed_addons
from app.addons.dependencies import get_connector_registry, get_loader
from app.db.session import SessionLocal
```

Edit the existing `lifespan` function — insert the bootstrap call before the scheduler block. The function now looks like:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        with SessionLocal() as session:
            bootstrap_installed_addons(
                session=session,
                loader=get_loader(),
                registry=get_connector_registry(),
            )
    except Exception:
        logger.exception("addon_bootstrap_unhandled")

    task: asyncio.Task | None = None
    if _settings.fortigate_ingestion_scheduler_enabled:
        task = asyncio.create_task(_fortigate_ingestion_scheduler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
```

The bootstrap is synchronous and short — running it before yielding is safe and matches the convention of "do init work, then yield, then teardown."

- [ ] **Step 3: Rebuild and verify the log line on startup**

```bash
docker compose up -d --build api
sleep 5
docker compose logs api --tail=80 | grep -i addon_bootstrap_loaded
```

Expected: a line `addon_bootstrap_loaded count=0` (no installs yet).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/addons/bootstrap.py apps/api/app/main.py
git commit -m "feat(addons): bootstrap installed packages on api startup"
```

---

## Task 11: Docker volume + env var wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example` (if it exists)

- [ ] **Step 1: Add the named volume**

Open `docker-compose.yml`. Under the `api` service `volumes:` list, add:

```yaml
      - addons_data:/app/data/addons
```

Under the `api` service `environment:` (create the block if missing), add:

```yaml
      MARKETPLACE_GH_TOKEN: ${MARKETPLACE_GH_TOKEN:-}
```

At the bottom of the file, under (or creating) the top-level `volumes:` block, add:

```yaml
  addons_data:
```

- [ ] **Step 2: Document the env var**

If `.env.example` exists at the repo root, append:

```
MARKETPLACE_GH_TOKEN=ghp_replace_me_with_repo_read_scope_token
```

If no `.env.example`, skip. Do NOT commit a real token.

- [ ] **Step 3: Recreate the container and verify the volume**

```bash
docker compose up -d --build api
docker compose exec -T api ls -la /app/data/addons
```

Expected: directory exists and is empty (or `/app/data/addons` contains a `.` entry).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example 2>/dev/null || git add docker-compose.yml
git commit -m "feat(addons): docker volume + MARKETPLACE_GH_TOKEN env"
```

---

## Task 12: End-to-end install integration test

**Files:**
- Create: `apps/api/tests/test_marketplace_install_endpoint.py`

This test exercises router + service + loader + registry together against a stubbed GitHub API. It uses dependency overrides to inject the test transport so no real HTTP happens.

- [ ] **Step 1: Write the integration test**

Create `apps/api/tests/test_marketplace_install_endpoint.py`:

```python
import io
import json
import tarfile
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.addons.catalog_fetcher import CatalogFetcher
from app.addons.dependencies import (
    get_catalog_fetcher,
    get_connector_registry,
    get_install_service,
    get_loader,
)
from app.addons.install_service import InstallService
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.dependencies import get_current_api_user, require_admin_user
from app.main import app


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
    catalog = CatalogFetcher(repo="ping-wins/penguard-addons", token="t", transport=transport)
    service = InstallService(
        session_factory=lambda: __import__("app.db.session", fromlist=["SessionLocal"]).SessionLocal(),
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
```

- [ ] **Step 2: Run the test to verify the full stack**

```bash
docker compose exec -T api uv run pytest tests/test_marketplace_install_endpoint.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Run the full add-on test suite once**

```bash
docker compose exec -T api uv run pytest tests/test_addon_manifest_schema.py tests/test_installed_store.py tests/test_addon_loader.py tests/test_addon_catalog_fetcher.py tests/test_addon_install_service.py tests/test_addon_registry_runtime.py tests/test_marketplace_install_endpoint.py -v
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_marketplace_install_endpoint.py
git commit -m "test(addons): end-to-end install/list/uninstall through FastAPI"
```

---

## Done criteria for Plan A

- All 12 task suites green under `pytest`.
- `docker compose up -d --build api` brings the API up with `addon_bootstrap_loaded count=0` log line.
- `POST /api/marketplace/addons/{id}/install` with a valid mock returns `200` and persists a row; subsequent `GET /api/marketplace/addons` surfaces `installed: true`.
- `DELETE /api/marketplace/addons/{id}` reverses everything.
- FortiGate behaviour unchanged — existing tests in `tests/test_fortigate_*.py` still pass.

Run as final gate:

```bash
docker compose exec -T api uv run pytest -q
```

Expected: full suite green.
