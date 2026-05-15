# Marketplace add-on packages

**Date:** 2026-05-14
**Status:** design — awaiting user review
**Repos affected:** `ping-wins/FortiDashboard`, `ping-wins/fortidashboard-addons`

## Problem

The marketplace foundation today ships only a JSON manifest per add-on. The
FortiGate connector code (HTTP client, normalizers, widget data, SIEM
ingestion) lives in `apps/api/app/integrations/fortigate/` inside the
monorepo. That makes the marketplace a catalog, not a package manager — you
can browse manifests but you cannot actually add support for a new vendor
without shipping a new dashboard build.

The desired model: each add-on is a **self-contained package** that bundles
its manifest, connector code, and fixtures. The dashboard ships with zero
vendor connectors. Browsing the marketplace and clicking "Install" downloads
that package, registers it, and dynamically loads the connector at runtime.
Uninstall reverses everything.

## Goals

- Replace the manifest-only marketplace with a package-based install flow.
- Move FortiGate vendor code out of the monorepo into the first
  add-on package, hosted in `ping-wins/fortidashboard-addons`.
- Keep the install/uninstall surface small (3 endpoints) and the loader
  isolated (no `sys.path` pollution, no global state past the registry).
- Provide a clean migration that does not force users to re-configure their
  existing FortiGate integrations.

## Non-goals (MVP)

- Multiple versions of the same add-on installed simultaneously.
- Auto-installing pinned Python dependencies (`requirements.txt` is
  informative only — the dashboard environment must already satisfy them).
- Frontend widget code (Vue components) inside packages. Widgets stay in
  the dashboard repo, referenced by id from the manifest. A frontend
  plugin runtime is roadmap.
- Cryptographic signing of packages. Trust is rooted in GitHub org ACLs.
- Sandboxing of add-on code. Add-ons run in the same Python process as
  the API.

## Architecture overview

```
ping-wins/fortidashboard-addons        # registry repo (private)
  catalog.json                         # lightweight index
  fortigate-core/
    7.6.0/
      addon.json
      connector/   (Python package)
      fixtures/
      requirements.txt
  git tag: fortigate-core-v7.6.0

           │  GitHub API tarball
           ▼

Dashboard API
  POST   /api/marketplace/addons/{id}/install   body: {"version": "..."}
  DELETE /api/marketplace/addons/{id}
  GET    /api/marketplace/addons                (catalog + install state)

  catalog_svc ──▶ install_svc ──▶ loader (importlib)
                                  │
                                  ▼
                            /app/data/addons/<id>/<version>/
                            installed_addons table

           │ at request time
           ▼
  ConnectorRegistry.get(addon_id).get_widget_data(req)
  ConnectorRegistry.get(addon_id).ingest_events(since)
```

Single active version per add-on. Re-install replaces the previous version.

## Package format

Layout in `fortidashboard-addons`:

```
fortidashboard-addons/
├── catalog.json
├── README.md
└── fortigate-core/
    └── 7.6.0/
        ├── addon.json
        ├── connector/
        │   ├── __init__.py             # exports get_connector(config)
        │   ├── client.py
        │   ├── normalizers.py
        │   ├── widgets_data.py
        │   └── siem.py                 # AddonConnector impl
        ├── fixtures/
        │   └── system_status.json
        ├── requirements.txt
        └── CHANGELOG.md
```

### `catalog.json` (repo root)

```json
{
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
      "tagTemplate": "fortigate-core-v{version}"
    }
  ]
}
```

The dashboard catalog endpoint reads only this file. One request per refresh,
TTL 5 minutes in memory.

### `addon.json` (per version)

Existing schema (`apps/api/app/addons/manifest.py`) plus two new fields:

| Field           | Type             | Purpose                                      |
|-----------------|------------------|----------------------------------------------|
| `entrypoint`    | string           | Subdir to import (default `connector`)       |
| `requirements`  | list[string]     | Informative pinned deps for validation       |

Existing `compatibility` block (FortiOS `minProviderVersion`, tested
versions, notes) is retained.

### Connector contract

`connector/__init__.py` MUST export:

```python
def get_connector(config: dict) -> "AddonConnector": ...
```

The connector duck-types the `AddonConnector` Protocol defined in the
dashboard at `apps/api/app/addons/contracts.py`:

```python
class AddonConnector(Protocol):
    def health_check(self) -> dict[str, Any]: ...
    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]: ...
    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
```

Inputs and outputs are plain dicts (or JSON-serializable types) so the
package has zero dashboard-side imports. The dashboard wraps responses
into concrete pydantic models (`HealthCheckResult`, `WidgetDataRequest`,
`SiemEvent`) on its side — those types do not cross the package boundary.

This keeps the connector portable, dashboard-version-independent, and
trivially serializable for future out-of-process execution (sandbox /
gRPC roadmap).

## Fetch + storage

### Catalog fetch

```
GET https://api.github.com/repos/ping-wins/fortidashboard-addons/contents/catalog.json
Authorization: Bearer $MARKETPLACE_GH_TOKEN
Accept: application/vnd.github.raw+json
```

5-minute in-memory TTL. `/api/marketplace/addons` joins the cached catalog
with the `installed_addons` table to set per-addon `installed: true|false`
and `installedVersion: "7.6.0"`.

### Install fetch

```
GET https://api.github.com/repos/ping-wins/fortidashboard-addons/tarball/<tag>
tag = "<addon-id>-v<version>"
```

Fetches the whole repo at that tag (small — manifests + Python). Loader
extracts only the `<addon-id>/<version>/` subtree and discards the rest.

### Storage

Named Docker volume `addons_data` mounted at `/app/data/addons`:

```
/app/data/addons/
├── <addon-id>/
│   └── <version>/
│       ├── addon.json
│       ├── connector/...
│       └── .install.json     # {tag, sha256, installed_at}
├── .tmp/                     # extraction staging
└── .trash/                   # 24h soft-delete on uninstall
```

`docker-compose.yml` declares the named volume so it survives container
recreation but is local to the host.

### Install flow (atomic)

1. Resolve `(id, version)` to tag, stream tarball.
2. Verify sha256 of tarball (recorded; no signature check yet).
3. Extract into `/app/data/addons/.tmp/<uuid>/`.
4. Validate: `addon.json` parses, `addon.json.version` matches dirname,
   top-level dirname matches `id`, `entrypoint` resolves to a directory
   under the package root (reject if it contains `..` or absolute path
   components — defends against path-traversal in a hostile manifest).
5. If `<addon-id>/<old-version>/` already present, move it to
   `.trash/<addon-id>/<old-version>-<ts>/`.
6. Move `.tmp/<uuid>/<addon-id>/<version>/` to
   `/app/data/addons/<addon-id>/<version>/` (atomic rename within the same
   filesystem).
7. Call `loader.load(install)`. On success, upsert `installed_addons`.
8. On any failure: clean `.tmp`, leave existing install untouched, return
   typed error to caller.

### Uninstall flow

`loader.unload(addon_id)` → move dir to `.trash` → `DELETE` row. `.trash`
swept by a daily job (out of scope; manual rm acceptable for MVP).

## Dynamic loader

`apps/api/app/addons/loader.py`:

```python
class AddonLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, ModuleType] = {}

    def load(self, install: InstalledAddon) -> Callable[[dict], AddonConnector]:
        addon_root = Path(install.path)
        manifest = AddonManifest.model_validate_json(
            (addon_root / "addon.json").read_text(encoding="utf-8")
        )
        entry_dir = addon_root / (manifest.entrypoint or "connector")
        entry = entry_dir / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            f"fortidashboard_addons.{install.id}",
            entry,
            submodule_search_locations=[str(entry_dir)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        if not callable(getattr(module, "get_connector", None)):
            raise AddonLoadError("addon missing get_connector()")
        self._loaded[install.id] = module
        return module.get_connector

    def unload(self, addon_id: str) -> None:
        mod = self._loaded.pop(addon_id, None)
        if mod is not None:
            sys.modules.pop(mod.__name__, None)
```

`submodule_search_locations` lets the package use relative imports
(`from .client import ...`) without touching `sys.path`.

### Boot bootstrap

On API startup, iterate `installed_addons` and call `loader.load` for each.
Failures are logged with the add-on id and version and the row is marked
`status=error`. Other add-ons still load. The API does not exit.

### Reload on update

Re-install path calls `loader.unload(id)` before `loader.load(new)`. If
`active_requests[id] > 0` the install returns `409` and asks the operator
to retry. Graceful drain is roadmap.

## Connector registry

```python
class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[dict], AddonConnector]] = {}
        self._instances: dict[tuple[str, str], AddonConnector] = {}

    def register(self, addon_id: str, factory: Callable[[dict], AddonConnector]) -> None: ...
    def unregister(self, addon_id: str) -> None: ...
    def get(self, addon_id: str, integration_id: str, config: dict) -> AddonConnector: ...
```

Cache key `(addon_id, integration_id)`. Configs come from the existing
integrations store. Connectors are stateless w.r.t. the DB — the store
hands them config; they hand back data.

## Migration: extract FortiGate to package

### In `fortidashboard-addons` repo

1. Create `fortigate-core/7.6.0/` with the new layout.
2. Copy `client.py`, `normalizers.py` verbatim. Rename `widgets.py` to
   `widgets_data.py` (it is data generation, no Vue).
3. New `siem.py`: implements `AddonConnector`. Wraps `FortiGateApiClient`.
   `get_widget_data` dispatches by `widget_id`. `ingest_events` returns
   `auth.failed_login` + IPS events. `health_check` exercises
   `system_status`.
4. `__init__.py` exports `get_connector(config)`.
5. Bump the manifest `version` field from `0.2.0` → `1.0.0` to mark the
   transition from manifest-only to packaged add-on. Add
   `entrypoint: "connector"` and `requirements: ["httpx>=0.27,<1.0"]`.
   The pydantic schema treats both new fields as optional (default
   `entrypoint = "connector"`, `requirements = []`) so it stays
   backwards-compatible with older manifests if any are encountered.
6. Tag `fortigate-core-v7.6.0`, push.

### In dashboard monorepo

1. Add new modules:
   - `apps/api/app/addons/contracts.py` — Protocols and DTOs.
   - `apps/api/app/addons/loader.py` — `AddonLoader`.
   - `apps/api/app/addons/install_service.py` — fetch + extract + register.
   - `apps/api/app/addons/registry_runtime.py` — `ConnectorRegistry`.
   - DB migration: `installed_addons (id PK, version, installed_at, path, sha256, tag, status)`.

2. Update routes:
   - `POST /api/marketplace/addons/{id}/install` (admin) — body `{version}`.
   - `DELETE /api/marketplace/addons/{id}` (admin).
   - `GET /api/marketplace/addons` (any user) — merges catalog with
     `installed_addons` to surface `installed` / `installedVersion`.
   - `POST /api/marketplace/addons/refresh` stays (admin, clears catalog
     cache).

3. Remove vendor code:
   - Delete `apps/api/app/integrations/fortigate/{client,normalizers,
     widgets}.py`.
   - Rename `apps/api/app/integrations/fortigate/store.py` to
     `apps/api/app/integrations/store.py`. The store stays in the
     dashboard (DB persistence is core, not vendor-specific).
   - Replace `service.py` with a thin shim that delegates to
     `ConnectorRegistry`. Eventually deleted when all call sites migrate
     to the registry directly.

4. Update call sites:
   - Widget endpoints currently importing
     `app.integrations.fortigate.widgets` → call
     `registry.get("fortigate-core", integration_id, config).get_widget_data(req)`.
   - SIEM ingestion job → loop `installed_addons`, call `ingest_events`.

5. One-time auto-install:
   - On API boot, if `installed_addons` is empty AND there exists at least
     one FortiGate integration row in the integrations store, queue an
     install of `fortigate-core@<latestVersion-from-catalog>` and log a
     migration line. User-invisible.

6. Frontend:
   - `MarketplacePanel.vue` — add `Installed` badge sourced from
     `installed: true` flag. Hook `Install` button to the install endpoint
     with progress indication.
   - Existing FortiGate widget Vue components stay where they are. They
     read widget data from `/api/widgets/...`, which now routes via the
     registry — no frontend change required there.

## Trust model + security

- Repo `ping-wins/fortidashboard-addons` is private. Only org members can
  push.
- Dashboard authenticates with a PAT in `MARKETPLACE_GH_TOKEN`
  (`repo:read` scope). Token rotatable via env without rebuild.
- Tarball sha256 stored in `.install.json` for post-install audit. No
  signature verification at MVP.
- Filesystem permissions: `/app/data/addons` writable only by the API
  user.
- Endpoint permissions:
  - Install / uninstall / refresh → `require_admin_user`.
  - List → authenticated user.
- Accepted risks (MVP):
  - A malicious org member could push RCE. Mitigated by GitHub branch
    protection on `main` (required reviews) — not configured by this
    design, must be set on the registry repo before first non-trivial
    add-on lands.
  - Dependencies in `requirements.txt` are informative only; missing
    deps cause `ModuleNotFoundError` at import. Considered a clear
    failure mode.
- Roadmap (out of MVP): sigstore/cosign signing, sandboxed exec, isolated
  venv per add-on.

## Testing strategy

### Unit (dashboard)

- `AddonLoader.load` with a tmpdir fixture add-on. Confirms namespacing
  (`fortidashboard_addons.<id>` only) and no leakage into other modules.
- `AddonLoader.unload` cleans `sys.modules`.
- `ConnectorRegistry` lookup and error paths (404 on unknown id).
- `install_service` happy path; rollback when sha mismatch / extract
  fails / validation fails.
- Catalog fetch with `httpx.MockTransport`: 200, 401, timeout, malformed
  JSON.

### Integration (dashboard + fake registry)

- httpx mock returns a synthetic tarball assembled in memory holding a
  `test-provider-v1.0.0` add-on (minimal Protocol-compliant
  `get_connector`).
- Full round-trip: install → loader registers → widget data fetch via
  registry → uninstall → loader cleans up.

### Package CI (`fortidashboard-addons` repo)

- Each `<id>/<version>/tests/` runs `pytest` against local fixtures with
  `respx`. CI workflow on the registry repo runs them per push to ensure
  manifests + connectors stay valid before a tag is cut.

### Manual smoke post-deploy

1. Reset cockpit so no integrations exist.
2. Open marketplace → see `fortigate-core` listed as not installed.
3. Click Install → progress → "Installed v7.6.0".
4. Configure a FortiGate integration → connect → widgets render with live
   data.
5. Uninstall → widgets switch to "addon not installed" state cleanly.

## Open questions

None at write time. Items deferred to roadmap are listed under non-goals
and in §7 (trust roadmap) / §4 (graceful reload). If any deferred item
surfaces as a hard requirement during planning it must come back here as
an amendment.

## Affected files (preview, not exhaustive)

Dashboard:

- `apps/api/app/addons/contracts.py` (new)
- `apps/api/app/addons/loader.py` (new)
- `apps/api/app/addons/install_service.py` (new)
- `apps/api/app/addons/registry_runtime.py` (new)
- `apps/api/app/addons/manifest.py` (add `entrypoint`, `requirements`)
- `apps/api/app/addons/registry.py` (deprecate local-dir loader; replace
  with installed-addons-driven loader)
- `apps/api/app/routers/marketplace.py` (add install/uninstall)
- `apps/api/app/db/migrations/...` (new `installed_addons` table)
- `apps/api/app/integrations/fortigate/{client,normalizers,widgets}.py`
  (deleted)
- `apps/api/app/integrations/fortigate/service.py` (shim → registry)
- `apps/api/app/integrations/store.py` (renamed from
  `integrations/fortigate/store.py`)
- `apps/web/src/components/marketplace/MarketplacePanel.vue` (install
  button + installed badge)
- `apps/web/src/stores/useMarketplaceStore.ts` (install action)
- `docker-compose.yml` (named volume `addons_data`)
- `addons/` (deleted from monorepo; superseded by remote registry)

Registry repo (`fortidashboard-addons`):

- `catalog.json` (new)
- `fortigate-core/7.6.0/{addon.json, connector/, fixtures/,
  requirements.txt, CHANGELOG.md}` (new)
- `fortigate-core/7.6.0/tests/` (new)
- `.github/workflows/validate.yml` (new — runs pytest per package)
- Tag `fortigate-core-v7.6.0`
