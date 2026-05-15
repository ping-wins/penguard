# Marketplace add-on packages

Authoritative overview of how add-ons are described, hosted, fetched, and
loaded by FortiDashboard. Replaces the manifest-only model in
`docs/marketplace-plan.md` (kept as historical reference).

## Direction in one paragraph

The dashboard ships **zero vendor connectors**. Each provider integration
(FortiGate, Palo Alto, Cisco, ...) is a self-contained **package** —
manifest + Python connector code + fixtures — published in the registry
repo `ping-wins/fortidashboard-addons`. The marketplace UI in
`apps/web/src/components/marketplace/MarketplacePanel.vue` shows
the catalog, and "Install" downloads the chosen package, extracts it onto
a Docker volume, registers it in the DB, and dynamically imports the
connector. From that point on, dashboard request handlers call the
connector through a process-wide `ConnectorRegistry` instead of reaching
into hand-rolled `apps/api/app/integrations/<vendor>/` modules.

## Where the pieces live

| Artifact | Location |
|----------|----------|
| Design spec (authoritative) | `docs/superpowers/specs/2026-05-14-marketplace-addon-packages-design.md` |
| Plan A — backend infrastructure | `docs/superpowers/plans/2026-05-14-marketplace-addon-packages-plan-a-backend-infra.md` |
| Plan B — FortiGate extraction & auto-migration | (to be written after Plan A merges) |
| Plan C — Frontend install UX | (to be written after Plan A merges) |
| Registry repo (private) | https://github.com/ping-wins/fortidashboard-addons |
| Backend code (Plan A target) | `apps/api/app/addons/` |
| Frontend marketplace UI | `apps/web/src/components/marketplace/MarketplacePanel.vue` |

## What's done vs. what's pending

| Step | Status |
|------|--------|
| Manifest schema (`AddonManifest` + `compatibility`) | Done — `apps/api/app/addons/manifest.py` |
| Local-dir manifest registry (legacy, manifest-only) | Done — `apps/api/app/addons/registry.py` |
| Marketplace tab in Settings modal | Done — `MarketplacePanel.vue` |
| Private registry repo `ping-wins/fortidashboard-addons` | Done — repo created, README + `fortigate/addon.json` v0.2.0 pushed |
| **Backend Plan A** (loader, install service, DB table, endpoints) | **Pending — plan written** |
| **Plan B** FortiGate extraction + auto-install on boot | Pending — not yet planned |
| **Plan C** Frontend install button + installed badge | Pending — not yet planned |
| Cryptographic package signing | Roadmap (post-MVP) |
| Frontend widget code shipped inside packages | Roadmap (needs plugin runtime) |
| Multi-version side-by-side install | YAGNI (not planned) |

## How to read the design

If you are about to write or review code in this area, read in this
order:

1. `docs/superpowers/specs/2026-05-14-marketplace-addon-packages-design.md` —
   the contract: package layout, install flow, loader semantics, trust
   model.
2. The plan file for the phase you are working on (`plan-a-*`,
   `plan-b-*`, `plan-c-*`).
3. The current code under `apps/api/app/addons/` to see where you fit.

## Decisions already taken

These are locked unless the design spec is amended. Do not relitigate in
PRs — open an issue + amend the spec first.

- **Package contents = real Python code.** Not a declarative-only
  manifest. Connector code is dynamically imported in-process. Trust is
  rooted in GitHub org ACLs on `ping-wins`.
- **FortiGate code moves out of the monorepo.** Plan B deletes
  `apps/api/app/integrations/fortigate/{client,normalizers,widgets}.py`
  and ships them inside the `fortigate-core` package instead. The
  integrations store (DB persistence of integrations) stays in the
  monorepo — it is core, not vendor-specific.
- **Fetch = GitHub API tarball by git tag** (`<addon-id>-v<version>`).
  No release-asset publishing. Git tag is the version source of truth.
- **Storage = Docker named volume** `addons_data` at
  `/app/data/addons/<id>/<version>/`.
- **Loader = `importlib.util.spec_from_file_location`** with namespace
  `fortidashboard_addons.<id>`. No `sys.path` pollution.
- **One active version per add-on.** Re-install replaces.
- **Connector contract = duck-typed `Protocol`.** Packages return plain
  dicts. Dashboard wraps into typed models on its side. Zero
  dashboard-side imports inside the package.
- **Frontend widgets stay in the dashboard.** They consume widget data
  from the existing `/api/widgets/...` endpoints, which Plan B reroutes
  through the `ConnectorRegistry`. A frontend plugin runtime is
  roadmap, not MVP.

## Working in this area: rules of engagement

- **Do not extend the bundled local-dir registry** (`apps/api/app/addons/registry.py`)
  with new vendor manifests — the bundled `addons/<id>/` directory is
  the transitional surface. New add-ons go to the registry repo as
  packages.
- **Do not import `apps/api/app/integrations/fortigate/` from new code.**
  After Plan B, those modules are gone. Use the `ConnectorRegistry`.
- **Manifest schema changes** (adding fields, changing types) require
  bumping both `addon.json.version` in every existing package AND
  marking the dashboard schema as backwards-compatible (optional fields
  with defaults). The local-dir loader and the installed-package loader
  must both keep parsing older manifests.
- **No `requirements.txt` auto-install.** Packages list their pinned
  deps for documentation; the dashboard environment must already
  satisfy them. Missing deps surface as a clear `ModuleNotFoundError`
  at import time. Adding `pip install` per-add-on is roadmap (needs a
  venv-per-package design first).
- **Backend container rebuilds.** The API container has no source bind
  mount — `docker compose up -d --build api` after every backend edit
  (see `MEMORY.md`).

## Glossary

| Term | Meaning |
|------|---------|
| **Add-on** | A versioned provider integration package (manifest + connector code). |
| **Manifest** | The `addon.json` file at a package root. |
| **Package** | A directory named `<addon-id>/<version>/` containing the manifest, the Python connector subdir, and fixtures. |
| **Registry repo** | `ping-wins/fortidashboard-addons` — the catalog of packages. |
| **Catalog** | `catalog.json` at the registry-repo root listing all add-ons + their versions. |
| **Connector** | The Python entry point exposed by a package via `get_connector(config) -> AddonConnector`. |
| **`ConnectorRegistry`** | Dashboard-side in-process registry that maps `addon_id` to a connector factory. |
| **`InstalledAddon`** | DB row recording what is currently installed (id, version, path, tag, sha256). |
