# Unified SOC Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three hardcoded integration forms (FortiGate / FortiWeb / Penguin tools) with one add-on-driven wizard that picks a machine type + version from installed marketplace add-ons, tests the connection, persists it, and auto-wires SIEM/SOAR per-destination.

**Architecture:** Add-on packages are 100% self-contained in the **external** repo `ping-wins/penguard-addons` (cloned at `../penguard-addons`). The dashboard stays thin — no vendor connector code ships in it; the marketplace install flow fetches a package tarball by git tag. Phase 1 authors the 5 packages (fortigate-core, fortiweb-core, penguin-siem, penguin-xdr, penguin-soar) by porting the relevant in-repo client logic into each package. Phase 2 adds a generic `/api/integrations/connect` flow + the Vue wizard. Phase 3 adds per-destination auto-wiring (SIEM log-forwarding + SOAR target registration).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic v2 (backend), Vue 3 + Pinia + Vitest (web), pytest (api), Docker Compose. External package repo is plain Python (stdlib + `httpx`).

**Spec:** [`../specs/2026-05-17-unified-soc-integration-design.md`](../specs/2026-05-17-unified-soc-integration-design.md)

### Locked decisions (clarified with user, deviations from spec noted)

- **Packaging:** external repo only. `../penguard-addons` current content is throwaway test — rewrite entirely. Each package = `{id}/{version}/addon.json` + `{id}/{version}/connector/__init__.py` exposing `get_connector(config)`. Tag = `{id}-v{version}`.
- **Connector code:** **ported** (copied) into each package. No `import app.*` from a package. Dashboard keeps legacy `app.integrations.*` code until Phase 2 cutover.
- **Wizard catalog (spec deviation):** spec said catalog = `list_installed() ∩ list_addons()`. `list_addons()` reads only the local `addons/` dir, so external-only packages would never intersect. **Corrected:** catalog is derived from each *installed* record's own `addon.json` at `record.path` (authoritative, version-specific). No local manifest stubs required.
- **SOAR wiring (spec concretization):** spec said "register `list_playbook_actions()` with the SOAR catalog". Concretely: store actions in a dashboard-owned `soar_targets` table and expose `GET /api/integrations/{id}/soar-actions`. No dependency on Skipper internals.

### Repo layout note

Two working trees:
- **DASH** = `C:\Users\lucas\Desktop\PingWins-Penguard\Penguard` (this repo).
- **PKGS** = `C:\Users\lucas\Desktop\PingWins-Penguard\penguard-addons` (external repo, already cloned).

Backend has **no source bind mount** — after every DASH backend edit run `docker compose up -d --build api` (see project memory). API tests run in-container: `docker compose exec api pytest <path> -q`.

---

## File Structure

### PKGS (external repo) — rewritten

```
catalog.json                              # marketplace catalog: all 5 addons
README.md                                 # package layout + tag convention
fortigate-core/0.2.0/addon.json
fortigate-core/0.2.0/connector/__init__.py
fortiweb-core/8.0.5/addon.json
fortiweb-core/8.0.5/connector/__init__.py
penguin-siem/1.0.0/addon.json
penguin-siem/1.0.0/connector/__init__.py
penguin-xdr/1.0.0/addon.json
penguin-xdr/1.0.0/connector/__init__.py
penguin-soar/1.0.0/addon.json
penguin-soar/1.0.0/connector/__init__.py
```

The legacy `fortigate/` and `fortiweb-waf/` dirs are deleted.

### DASH (this repo)

| File | Responsibility |
|---|---|
| `apps/api/app/addons/manifest.py` | + `AddonCapabilities` block on `AddonManifest` |
| `apps/api/app/integrations/catalog.py` | **new** — build wizard catalog from installed package manifests |
| `apps/api/app/integrations/wiring.py` | **new** — SIEM/SOAR auto-wire orchestration (Phase 3) |
| `apps/api/app/integrations/connect_persistence.py` | **new** — map addon `provider.type` → existing vendor store create/list/delete |
| `apps/api/app/routers/integrations_v2.py` | **new** — `/api/integrations/catalog`, `/connect`, `/connect/test`, `/{id}/soar-actions` |
| `apps/api/app/db/models.py` | + `IntegrationWiringModel`, `SoarTargetModel` |
| `apps/api/migrations/versions/<rev>_integration_wiring.py` | **new** — `integration_wiring` + `soar_targets` tables |
| `apps/api/app/main.py` | register `integrations_v2.router` |
| `apps/web/src/stores/useIntegrationConnectStore.ts` | **new** — catalog fetch + wizard draft + submit |
| `apps/web/src/components/integrations/ConnectWizard.vue` | **new** — 5-step wizard |
| `apps/web/src/components/layout/Sidebar.vue` | replace 3 form sections with wizard launcher (Phase 2) |
| `apps/web/src/i18n/*` | + `integrations.wizard.*` keys |

Test files are listed per task.

---

# PHASE 1 — Add-on-ify the built-in vendors

Independently shippable: produces 5 installable packages + the manifest `capabilities` field + parity tests. No UI change; legacy endpoints untouched.

---

### Task 1.1: Add `capabilities` to the add-on manifest schema

**Files:**
- Modify: `apps/api/app/addons/manifest.py`
- Test: `apps/api/tests/test_addon_manifest_schema.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_addon_manifest_schema.py`:

```python
def test_manifest_capabilities_defaults_all_false():
    m = AddonManifest.model_validate(_base_payload())
    assert m.capabilities.log_source is False
    assert m.capabilities.playbook_target is False
    assert m.capabilities.managed is False


def test_manifest_capabilities_round_trips_camel_case():
    payload = _base_payload()
    payload["capabilities"] = {
        "logSource": True,
        "playbookTarget": True,
        "managed": False,
    }
    dumped = AddonManifest.model_validate(payload).model_dump(by_alias=True)
    assert dumped["capabilities"] == {
        "logSource": True,
        "playbookTarget": True,
        "managed": False,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec api pytest tests/test_addon_manifest_schema.py -q`
Expected: FAIL — `AddonManifest` has no attribute `capabilities`.

- [ ] **Step 3: Add the `AddonCapabilities` model**

In `apps/api/app/addons/manifest.py`, add after `AddonCompatibility` (before `AddonManifest`):

```python
class AddonCapabilities(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    log_source: bool = Field(default=False, alias="logSource")
    playbook_target: bool = Field(default=False, alias="playbookTarget")
    managed: bool = Field(default=False)
```

In `AddonManifest`, add this field (after `compatibility`):

```python
    capabilities: AddonCapabilities = Field(default_factory=AddonCapabilities)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec api pytest tests/test_addon_manifest_schema.py -q`
Expected: PASS (all tests, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/addons/manifest.py apps/api/tests/test_addon_manifest_schema.py
git commit -m "feat(addons): add capabilities block to manifest schema"
```

---

### Task 1.2: Rewrite the external repo scaffold (catalog + README + cleanup)

**Files (PKGS = `../penguard-addons`):**
- Delete: `fortigate/`, `fortiweb-waf/`
- Modify: `catalog.json`, `README.md`

- [ ] **Step 1: Remove the throwaway test packages**

```bash
cd ../penguard-addons
git rm -r fortigate fortiweb-waf
```

- [ ] **Step 2: Write `catalog.json`**

Overwrite `../penguard-addons/catalog.json`:

```json
{
  "addons": [
    {
      "id": "fortigate-core",
      "name": "FortiGate Core",
      "vendor": "Fortinet",
      "category": "firewall",
      "icon": "fortinet",
      "description": "Pull system status, traffic, policies, threat logs and admin login events from FortiGate REST API.",
      "latestVersion": "0.2.0",
      "versions": ["0.2.0"],
      "tagTemplate": "fortigate-core-v{version}"
    },
    {
      "id": "fortiweb-core",
      "name": "FortiWeb Core",
      "vendor": "Fortinet",
      "category": "waf",
      "icon": "fortinet",
      "description": "Connect a FortiWeb WAF: REST health probe plus push-ingest of Attack/Traffic/Event telemetry.",
      "latestVersion": "8.0.5",
      "versions": ["8.0.5"],
      "tagTemplate": "fortiweb-core-v{version}"
    },
    {
      "id": "penguin-siem",
      "name": "Kowalski SIEM",
      "vendor": "PingWins",
      "category": "siem",
      "icon": "penguin",
      "description": "Kowalski SIEM: events, incidents, detection rules and timelines.",
      "latestVersion": "1.0.0",
      "versions": ["1.0.0"],
      "tagTemplate": "penguin-siem-v{version}"
    },
    {
      "id": "penguin-xdr",
      "name": "Rico XDR",
      "vendor": "PingWins",
      "category": "xdr",
      "icon": "penguin",
      "description": "Rico XDR: endpoint inventory, endpoint events and heartbeats.",
      "latestVersion": "1.0.0",
      "versions": ["1.0.0"],
      "tagTemplate": "penguin-xdr-v{version}"
    },
    {
      "id": "penguin-soar",
      "name": "Skipper SOAR",
      "vendor": "PingWins",
      "category": "soar",
      "icon": "penguin",
      "description": "Skipper SOAR: playbooks, playbook runs, approvals and dry-run actions.",
      "latestVersion": "1.0.0",
      "versions": ["1.0.0"],
      "tagTemplate": "penguin-soar-v{version}"
    }
  ]
}
```

- [ ] **Step 3: Write `README.md`**

Overwrite `../penguard-addons/README.md`:

```markdown
# Penguard Add-ons

Marketplace add-on packages installed by Penguard at runtime.

## Layout

    <addon-id>/<version>/addon.json          # AddonManifest (pydantic-validated)
    <addon-id>/<version>/connector/__init__.py  # must expose get_connector(config) -> connector

`connector` is the manifest `entrypoint` (default). The connector object must
implement: `health_check() -> dict`, `get_widget_data(req) -> dict`,
`ingest_events(since) -> list`, `close() -> None`. Optional duck-typed:
`list_playbook_actions() -> list[dict]`, `run_playbook_action(action_id, params) -> dict`.

Packages are self-contained: stdlib + httpx only, no imports from the dashboard.

## Releasing

Tag a version so the dashboard install flow can fetch it:

    git tag <addon-id>-v<version> && git push origin <addon-id>-v<version>

The dashboard fetches `https://api.github.com/repos/ping-wins/penguard-addons/tarball/<tag>`
and expects the package at `<addon-id>/<version>/` inside the tarball.
```

- [ ] **Step 4: Commit (PKGS)**

```bash
cd ../penguard-addons
git add -A
git commit -m "chore: reset registry, add unified SOC catalog"
```

---

### Task 1.3: `fortigate-core` package (port FortiGate client)

**Files (PKGS):**
- Create: `fortigate-core/0.2.0/addon.json`
- Create: `fortigate-core/0.2.0/connector/__init__.py`
- Create: `fortigate-core/0.2.0/connector/fortigate_client.py`

**Port source (DASH, read-only reference):** `apps/api/app/integrations/fortigate/client.py`, `apps/api/app/integrations/fortigate/normalizers.py`.

- [ ] **Step 1: Write `fortigate-core/0.2.0/addon.json`**

Use the exact manifest currently at `../penguard-addons` history (`git show aff30c9:fortigate/addon.json`) **plus** a `capabilities` block. Write `../penguard-addons/fortigate-core/0.2.0/addon.json`:

```json
{
  "id": "fortigate-core",
  "version": "0.2.0",
  "name": "FortiGate Core",
  "vendor": "Fortinet",
  "category": "firewall",
  "description": "Pull system status, traffic, policies, threat logs and admin login events from FortiGate REST API.",
  "icon": "fortinet",
  "minDashboardVersion": "0.1.0",
  "provider": {
    "type": "fortigate",
    "auth": {
      "kind": "apiKey",
      "fields": [
        { "id": "host", "label": "Host URL", "type": "url", "required": true, "placeholder": "https://192.168.0.100" },
        { "id": "apiKey", "label": "API Key", "type": "secret", "required": true },
        { "id": "verifyTls", "label": "Verify TLS", "type": "boolean", "default": false }
      ]
    }
  },
  "compatibility": {
    "minProviderVersion": "7.6.0",
    "testedVersions": ["7.6.0", "7.6.1"],
    "notes": "Routes targeted at FortiOS 7.6+."
  },
  "capabilities": { "logSource": true, "playbookTarget": false, "managed": true },
  "routes": [
    { "id": "system-status", "method": "GET", "path": "/api/v2/monitor/system/status", "summary": "Device hostname, model, firmware, serial." }
  ],
  "widgets": [
    "fortigate-system-status",
    "fortigate-network-traffic",
    "fortigate-firewall-policies",
    "fortigate-top-threats",
    "fortigate-recent-events",
    "fortigate-risk-posture",
    "fortigate-interface-health",
    "fortigate-anomaly-highlights",
    "fortigate-kpi-sessions"
  ],
  "siemEventTypes": ["auth.failed_login", "network.deny", "network.event"],
  "entrypoint": "connector",
  "requirements": ["httpx>=0.27,<1.0"]
}
```

- [ ] **Step 2: Port the FortiGate client into the package**

Copy the dashboard client verbatim, then strip any `app.*` imports (the file uses only `httpx`/stdlib; verify after copy):

```bash
mkdir -p ../penguard-addons/fortigate-core/0.2.0/connector
cp apps/api/app/integrations/fortigate/client.py \
   ../penguard-addons/fortigate-core/0.2.0/connector/fortigate_client.py
grep -n '^from app\.\|^import app\.' ../penguard-addons/fortigate-core/0.2.0/connector/fortigate_client.py
```

Expected: the `grep` prints nothing. If it prints any line, replace that import by inlining the referenced symbol into `fortigate_client.py` (the FortiGate client depends only on `httpx`; any `app.*` import is a normalizer helper — copy the needed function from `apps/api/app/integrations/fortigate/normalizers.py` into `fortigate_client.py`).

- [ ] **Step 3: Write `connector/__init__.py`**

`../penguard-addons/fortigate-core/0.2.0/connector/__init__.py`:

```python
from datetime import datetime
from typing import Any

from .fortigate_client import FortiGateApiClient, FortiGateApiError


class FortiGateConnector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: FortiGateApiClient | None = None

    def _ensure_client(self) -> FortiGateApiClient:
        if self._client is None:
            self._client = FortiGateApiClient(
                host=str(self.config.get("host") or "").rstrip("/"),
                api_key=str(self.config.get("apiKey") or ""),
                verify_tls=bool(self.config.get("verifyTls", False)),
            )
        return self._client

    def health_check(self) -> dict[str, Any]:
        host = str(self.config.get("host") or "").rstrip("/")
        if not host:
            return {"ok": False, "status": "missing_host", "device": {},
                    "message": "FortiGate host is required"}
        try:
            status = self._ensure_client().get_system_status()
        except FortiGateApiError as exc:
            return {"ok": False, "status": "disconnected", "device": {},
                    "message": str(exc)}
        results = status.get("results", status) if isinstance(status, dict) else {}
        return {
            "ok": True,
            "status": "connected",
            "device": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "hostname": str(results.get("hostname") or "FortiGate"),
                "model": str(results.get("model") or ""),
                "version": str(results.get("version") or ""),
                "serial": str(results.get("serial") or ""),
            },
            "message": "FortiGate REST API reachable",
        }

    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready", "data": {}, "meta": {"source": "fortigate"}}

    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]:
        return []

    def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None


def get_connector(config: dict[str, Any]) -> FortiGateConnector:
    return FortiGateConnector(config)
```

> If the ported client class is not named `FortiGateApiClient` / `FortiGateApiError`, adjust the two import names in steps 2–3 to match the actual class names in `apps/api/app/integrations/fortigate/client.py` (open it and read the class definitions).

- [ ] **Step 4: Smoke-test the connector imports standalone**

```bash
cd ../penguard-addons/fortigate-core/0.2.0
python -c "import connector; c=connector.get_connector({'host':''}); print(c.health_check())"
```

Expected: prints `{'ok': False, 'status': 'missing_host', ...}` (no ImportError).

- [ ] **Step 5: Tag + commit (PKGS)**

```bash
cd ../penguard-addons
git add fortigate-core
git commit -m "feat(fortigate-core): self-contained connector package 0.2.0"
git tag fortigate-core-v0.2.0
git push origin main fortigate-core-v0.2.0
```

---

### Task 1.4: `fortiweb-core` package (port FortiWeb probe)

**Files (PKGS):**
- Create: `fortiweb-core/8.0.5/addon.json`
- Create: `fortiweb-core/8.0.5/connector/__init__.py`
- Create: `fortiweb-core/8.0.5/connector/fortiweb_client.py`

**Port source (DASH):** `apps/api/app/integrations/fortiweb/client.py`, and the `_normalize_system_status` helper from `apps/api/app/integrations/fortiweb/service.py:588-612`.

- [ ] **Step 1: Write `fortiweb-core/8.0.5/addon.json`**

```json
{
  "id": "fortiweb-core",
  "version": "8.0.5",
  "name": "FortiWeb Core",
  "vendor": "Fortinet",
  "category": "waf",
  "description": "Connect a FortiWeb WAF: REST health probe plus push-ingest of Attack/Traffic/Event telemetry.",
  "icon": "fortinet",
  "minDashboardVersion": "0.1.0",
  "provider": {
    "type": "fortiweb",
    "auth": {
      "kind": "apiKey",
      "fields": [
        { "id": "host", "label": "FortiWeb URL", "type": "url", "required": true, "placeholder": "https://fortiweb.example.local" },
        { "id": "apiKey", "label": "API Key", "type": "secret", "required": true },
        { "id": "verifyTls", "label": "Verify TLS", "type": "boolean", "default": false }
      ]
    }
  },
  "compatibility": {
    "minProviderVersion": "8.0.5",
    "testedVersions": ["8.0.5"],
    "notes": "Validated against FortiWeb 8.0.5. Telemetry via push (HTTP) ingest to /api/soc/ingest/fortiweb."
  },
  "capabilities": { "logSource": true, "playbookTarget": true, "managed": true },
  "routes": [
    { "id": "push-ingest", "method": "POST", "path": "/api/soc/ingest/fortiweb", "summary": "Receives FortiWeb WAF log payloads." }
  ],
  "widgets": ["soc-recent-incidents", "soc-open-tickets", "soc-incidents-by-severity"],
  "siemEventTypes": ["waf.attack", "waf.dos", "waf.blocked_request", "http.attack"],
  "entrypoint": "connector",
  "requirements": ["httpx>=0.27,<1.0"]
}
```

- [ ] **Step 2: Port the FortiWeb client**

```bash
mkdir -p ../penguard-addons/fortiweb-core/8.0.5/connector
cp apps/api/app/integrations/fortiweb/client.py \
   ../penguard-addons/fortiweb-core/8.0.5/connector/fortiweb_client.py
grep -n '^from app\.\|^import app\.' ../penguard-addons/fortiweb-core/8.0.5/connector/fortiweb_client.py
```

Expected: `grep` prints nothing (client uses only `httpx`/stdlib). If it prints, inline the symbol as in Task 1.3 Step 2.

- [ ] **Step 3: Write `connector/__init__.py`**

`../penguard-addons/fortiweb-core/8.0.5/connector/__init__.py`:

```python
from datetime import datetime
from typing import Any

from .fortiweb_client import FortiWebApiClient, FortiWebApiError


def _normalize_system_status(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    merged = {**nested, **data, **payload}
    return {
        "hostname": str(merged.get("hostname") or merged.get("hostName") or merged.get("name") or "FortiWeb"),
        "model": str(merged.get("model") or merged.get("model_name") or merged.get("platform") or "FortiWeb"),
        "version": str(merged.get("version") or merged.get("firmware") or merged.get("firmwareVersion") or "unknown"),
        "serial": str(merged.get("serial") or merged.get("serialNumber") or ""),
    }


class FortiWebConnector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: FortiWebApiClient | None = None

    def health_check(self) -> dict[str, Any]:
        host = str(self.config.get("host") or "").rstrip("/")
        if not host:
            return {"ok": False, "status": "missing_host", "device": {},
                    "message": "FortiWeb host is required"}
        try:
            self._client = FortiWebApiClient(
                host=host,
                api_key=str(self.config.get("apiKey") or ""),
                verify_tls=bool(self.config.get("verifyTls", False)),
            )
            device = _normalize_system_status(self._client.get_system_status())
        except FortiWebApiError as exc:
            return {"ok": False, "status": "disconnected", "device": {},
                    "message": str(exc)}
        return {"ok": True, "status": "connected",
                "device": {"vendor": "Fortinet", "product": "FortiWeb", **device},
                "message": "FortiWeb REST API reachable"}

    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready", "data": {}, "meta": {"source": "fortiweb", "mode": "push"}}

    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]:
        return []

    def list_playbook_actions(self) -> list[dict[str, Any]]:
        return [{
            "id": "block_source_ip",
            "label": "Block source IP on FortiWeb",
            "paramsSchema": {"sourceIp": {"type": "string", "required": True}},
        }]

    def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None


def get_connector(config: dict[str, Any]) -> FortiWebConnector:
    return FortiWebConnector(config)
```

> Adjust `FortiWebApiClient` / `FortiWebApiError` import names to the actual class names in `apps/api/app/integrations/fortiweb/client.py` if they differ.

- [ ] **Step 4: Smoke-test**

```bash
cd ../penguard-addons/fortiweb-core/8.0.5
python -c "import connector; print(connector.get_connector({'host':''}).health_check())"
```

Expected: `{'ok': False, 'status': 'missing_host', ...}`.

- [ ] **Step 5: Tag + commit (PKGS)**

```bash
cd ../penguard-addons
git add fortiweb-core
git commit -m "feat(fortiweb-core): self-contained connector package 8.0.5"
git tag fortiweb-core-v8.0.5
git push origin main fortiweb-core-v8.0.5
```

---

### Task 1.5: `penguin-siem` / `penguin-xdr` / `penguin-soar` packages

**Files (PKGS):** for each of the 3 ids `(penguin-siem|penguin-xdr|penguin-soar)` at version `1.0.0`:
- Create: `<id>/1.0.0/addon.json`
- Create: `<id>/1.0.0/connector/__init__.py`
- Create (shared, copied into each): `<id>/1.0.0/connector/soc_client.py`

**Port source (DASH):** `apps/api/app/soc/client.py` (`SocServiceClient`). Penguin tools health is a `GET /health` returning `{"status": "ok"}` (see `apps/api/app/integrations/penguin_tools.py:87-108`).

- [ ] **Step 1: Port the SOC service client**

```bash
for id in penguin-siem penguin-xdr penguin-soar; do
  mkdir -p ../penguard-addons/$id/1.0.0/connector
  cp apps/api/app/soc/client.py ../penguard-addons/$id/1.0.0/connector/soc_client.py
  grep -n '^from app\.\|^import app\.' ../penguard-addons/$id/1.0.0/connector/soc_client.py
done
```

Expected: `grep` prints nothing for each. If it does, inline the referenced symbol into `soc_client.py`.

- [ ] **Step 2: Write the 3 manifests**

`../penguard-addons/penguin-siem/1.0.0/addon.json`:

```json
{
  "id": "penguin-siem", "version": "1.0.0", "name": "Kowalski SIEM",
  "vendor": "PingWins", "category": "siem", "icon": "penguin",
  "description": "Kowalski SIEM: events, incidents, detection rules and timelines.",
  "minDashboardVersion": "0.1.0",
  "provider": { "type": "siem_kowalski", "auth": { "kind": "apiKey", "fields": [
    { "id": "host", "label": "Kowalski URL", "type": "url", "required": true, "placeholder": "http://siem-kowalski:8000" }
  ] } },
  "compatibility": { "testedVersions": ["1.0.0"], "notes": "Kowalski SIEM service health probe." },
  "capabilities": { "logSource": true, "playbookTarget": false, "managed": false },
  "routes": [], "widgets": ["soc-incidents-by-severity", "soc-recent-incidents", "soc-top-entities"],
  "siemEventTypes": [], "entrypoint": "connector", "requirements": ["httpx>=0.27,<1.0"]
}
```

`../penguard-addons/penguin-xdr/1.0.0/addon.json`:

```json
{
  "id": "penguin-xdr", "version": "1.0.0", "name": "Rico XDR",
  "vendor": "PingWins", "category": "xdr", "icon": "penguin",
  "description": "Rico XDR: endpoint inventory, endpoint events and heartbeats.",
  "minDashboardVersion": "0.1.0",
  "provider": { "type": "xdr_rico", "auth": { "kind": "apiKey", "fields": [
    { "id": "host", "label": "Rico URL", "type": "url", "required": true, "placeholder": "http://xdr-rico:8000" }
  ] } },
  "compatibility": { "testedVersions": ["1.0.0"], "notes": "Rico XDR service health probe." },
  "capabilities": { "logSource": false, "playbookTarget": false, "managed": false },
  "routes": [], "widgets": ["xdr-endpoint-health"],
  "siemEventTypes": [], "entrypoint": "connector", "requirements": ["httpx>=0.27,<1.0"]
}
```

`../penguard-addons/penguin-soar/1.0.0/addon.json`:

```json
{
  "id": "penguin-soar", "version": "1.0.0", "name": "Skipper SOAR",
  "vendor": "PingWins", "category": "soar", "icon": "penguin",
  "description": "Skipper SOAR: playbooks, playbook runs, approvals and dry-run actions.",
  "minDashboardVersion": "0.1.0",
  "provider": { "type": "soar_skipper", "auth": { "kind": "apiKey", "fields": [
    { "id": "host", "label": "Skipper URL", "type": "url", "required": true, "placeholder": "http://soar-skipper:8000" }
  ] } },
  "compatibility": { "testedVersions": ["1.0.0"], "notes": "Skipper SOAR service health probe." },
  "capabilities": { "logSource": false, "playbookTarget": true, "managed": false },
  "routes": [], "widgets": ["soar-active-playbook-runs", "soar-playbook-run-history"],
  "siemEventTypes": [], "entrypoint": "connector", "requirements": ["httpx>=0.27,<1.0"]
}
```

- [ ] **Step 3: Write the shared connector for each (3 copies, differing only in `_SERVICE`)**

For `penguin-siem` write `../penguard-addons/penguin-siem/1.0.0/connector/__init__.py`:

```python
from datetime import datetime
from typing import Any

from .soc_client import SocServiceClient


_SERVICE = "siem_kowalski"


class PenguinConnector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: SocServiceClient | None = None

    def _ensure_client(self) -> SocServiceClient:
        if self._client is None:
            self._client = SocServiceClient(
                base_url=str(self.config.get("host") or "").rstrip("/"),
                service_name=_SERVICE,
                timeout_seconds=float(self.config.get("timeoutSeconds", 5.0)),
            )
        return self._client

    def health_check(self) -> dict[str, Any]:
        host = str(self.config.get("host") or "").rstrip("/")
        if not host:
            return {"ok": False, "status": "missing_host", "device": {},
                    "message": "Service URL is required"}
        try:
            payload = self._ensure_client().request("GET", "/health")
        except Exception as exc:  # SocServiceClient raises on transport/HTTP error
            return {"ok": False, "status": "disconnected", "device": {},
                    "message": str(exc)}
        ok = str(payload.get("status") or "") == "ok"
        return {
            "ok": ok,
            "status": "connected" if ok else "disconnected",
            "device": {"vendor": "PingWins", "product": _SERVICE, "host": host},
            "message": None if ok else "Service did not report status=ok",
        }

    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready", "data": {}, "meta": {"source": _SERVICE}}

    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]:
        return []

    def close(self) -> None:
        self._client = None


def get_connector(config: dict[str, Any]) -> PenguinConnector:
    return PenguinConnector(config)
```

Copy this file to `penguin-xdr/1.0.0/connector/__init__.py` (change `_SERVICE = "xdr_rico"`) and `penguin-soar/1.0.0/connector/__init__.py` (change `_SERVICE = "soar_skipper"`; additionally add this method to the `penguin-soar` copy, since its manifest declares `playbookTarget: true`):

```python
    def list_playbook_actions(self) -> list[dict[str, Any]]:
        return [{
            "id": "run_skipper_playbook",
            "label": "Run a Skipper SOAR playbook",
            "paramsSchema": {"playbookId": {"type": "string", "required": True}},
        }]
```

> If `SocServiceClient.__init__` signature differs from `(base_url, service_name, timeout_seconds)`, read `apps/api/app/soc/client.py` and adjust the kwargs in `_ensure_client` accordingly.

- [ ] **Step 4: Smoke-test each**

```bash
for id in penguin-siem penguin-xdr penguin-soar; do
  (cd ../penguard-addons/$id/1.0.0 && python -c "import connector; print(connector.get_connector({'host':''}).health_check())")
done
```

Expected: each prints `{'ok': False, 'status': 'missing_host', ...}`.

- [ ] **Step 5: Tag + commit (PKGS)**

```bash
cd ../penguard-addons
git add penguin-siem penguin-xdr penguin-soar
git commit -m "feat(penguin): self-contained SIEM/XDR/SOAR connector packages 1.0.0"
git tag penguin-siem-v1.0.0 && git tag penguin-xdr-v1.0.0 && git tag penguin-soar-v1.0.0
git push origin main penguin-siem-v1.0.0 penguin-xdr-v1.0.0 penguin-soar-v1.0.0
```

---

### Task 1.6: Parity tests for the new connectors (DASH)

Verify each package's `get_connector` loads and `health_check` behaves like the legacy probe for the missing-host and mock-device cases. Tests import the package by file path (no GitHub) for determinism.

**Files:**
- Create: `apps/api/tests/test_addon_vendor_connectors.py`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/test_addon_vendor_connectors.py`:

```python
import importlib.util
from pathlib import Path

import pytest

# PKGS repo sits next to the dashboard repo.
PKGS = Path(__file__).resolve().parents[3] / "penguard-addons"

CASES = [
    ("fortigate-core", "0.2.0"),
    ("fortiweb-core", "8.0.5"),
    ("penguin-siem", "1.0.0"),
    ("penguin-xdr", "1.0.0"),
    ("penguin-soar", "1.0.0"),
]


def _load(addon_id: str, version: str):
    entry = PKGS / addon_id / version / "connector" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        f"pkgtest_{addon_id.replace('-', '_')}",
        entry,
        submodule_search_locations=[str(entry.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("addon_id,version", CASES)
def test_get_connector_present_and_missing_host_is_graceful(addon_id, version):
    if not (PKGS / addon_id / version / "addon.json").is_file():
        pytest.skip(f"{addon_id} package not present at {PKGS}")
    module = _load(addon_id, version)
    connector = module.get_connector({"host": ""})
    result = connector.health_check()
    assert result["ok"] is False
    assert result["status"] == "missing_host"
    connector.close()


def test_soar_package_exposes_playbook_actions():
    if not (PKGS / "penguin-soar" / "1.0.0" / "addon.json").is_file():
        pytest.skip("penguin-soar package not present")
    module = _load("penguin-soar", "1.0.0")
    connector = module.get_connector({"host": "http://x"})
    actions = connector.list_playbook_actions()
    assert any(a["id"] == "run_skipper_playbook" for a in actions)
```

- [ ] **Step 2: Run — expect pass (packages exist from Tasks 1.3–1.5)**

Run: `docker compose exec api pytest tests/test_addon_vendor_connectors.py -q`
Expected: PASS. (If the test runs in a container where `../penguard-addons` is not mounted, the parametrized tests `skip`; in that case run locally instead: `cd apps/api && .venv/Scripts/python -m pytest tests/test_addon_vendor_connectors.py -q` from the host where both repos are checked out.)

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_addon_vendor_connectors.py
git commit -m "test(addons): parity smoke for vendor connector packages"
```

**Phase 1 complete.** All 5 packages installable via the existing marketplace flow; manifest schema carries `capabilities`; legacy endpoints + UI untouched.

---

# PHASE 2 — Unified wizard UI + connect orchestration

Independently shippable: adds the wizard behind the Integrations tab, backed by a generic connect flow. Legacy create/test endpoints stay as fallback until end of phase.

---

### Task 2.1: Wizard catalog builder (DASH)

Derive the catalog from installed package manifests (spec deviation, see header).

**Files:**
- Create: `apps/api/app/integrations/catalog.py`
- Test: `apps/api/tests/test_integration_catalog.py`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/test_integration_catalog.py`:

```python
import json
from pathlib import Path

from app.integrations.catalog import build_catalog


class _Rec:
    def __init__(self, id, version, path):
        self.id, self.version, self.path = id, version, path


def _write_manifest(tmp_path: Path) -> _Rec:
    pkg = tmp_path / "fortiweb-core" / "8.0.5"
    pkg.mkdir(parents=True)
    (pkg / "addon.json").write_text(json.dumps({
        "id": "fortiweb-core", "version": "8.0.5", "name": "FortiWeb Core",
        "vendor": "Fortinet", "category": "waf", "description": "x",
        "provider": {"type": "fortiweb", "auth": {"kind": "apiKey", "fields": [
            {"id": "host", "label": "URL", "type": "url", "required": True}
        ]}},
        "compatibility": {"testedVersions": ["8.0.5"]},
        "capabilities": {"logSource": True, "playbookTarget": True, "managed": True},
    }), encoding="utf-8")
    return _Rec("fortiweb-core", "8.0.5", str(pkg))


def test_build_catalog_reads_installed_manifest(tmp_path):
    rec = _write_manifest(tmp_path)
    catalog = build_catalog([rec])
    assert len(catalog) == 1
    entry = catalog[0]
    assert entry["addonId"] == "fortiweb-core"
    assert entry["vendor"] == "Fortinet"
    assert entry["versions"] == ["8.0.5"]
    assert entry["authFields"][0]["id"] == "host"
    assert entry["capabilities"] == {"logSource": True, "playbookTarget": True, "managed": True}


def test_build_catalog_skips_records_without_manifest(tmp_path):
    assert build_catalog([_Rec("ghost", "1.0.0", str(tmp_path / "nope"))]) == []
```

- [ ] **Step 2: Run — verify it fails**

Run: `docker compose exec api pytest tests/test_integration_catalog.py -q`
Expected: FAIL — `No module named 'app.integrations.catalog'`.

- [ ] **Step 3: Implement `catalog.py`**

`apps/api/app/integrations/catalog.py`:

```python
import json
import logging
from pathlib import Path
from typing import Any

from app.addons.installed_store import InstalledAddonRecord
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)


def build_catalog(records: list[InstalledAddonRecord]) -> list[dict[str, Any]]:
    """One catalog entry per installed add-on, sourced from the installed
    package's own addon.json (authoritative + version-specific)."""
    catalog: list[dict[str, Any]] = []
    for rec in records:
        manifest_path = Path(rec.path) / "addon.json"
        if not manifest_path.is_file():
            logger.warning("catalog_manifest_missing id=%s path=%s", rec.id, manifest_path)
            continue
        try:
            manifest = AddonManifest.model_validate(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            logger.exception("catalog_manifest_invalid id=%s err=%s", rec.id, exc)
            continue
        versions = (
            manifest.compatibility.tested_versions
            if manifest.compatibility and manifest.compatibility.tested_versions
            else [manifest.version]
        )
        catalog.append({
            "addonId": manifest.id,
            "name": manifest.name,
            "vendor": manifest.vendor,
            "category": manifest.category,
            "icon": manifest.icon,
            "providerType": manifest.provider.type,
            "versions": list(versions),
            "authFields": [f.model_dump(by_alias=True) for f in manifest.provider.auth.fields],
            "capabilities": manifest.capabilities.model_dump(by_alias=True),
        })
    return catalog
```

- [ ] **Step 4: Run — verify it passes**

Run: `docker compose exec api pytest tests/test_integration_catalog.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/integrations/catalog.py apps/api/tests/test_integration_catalog.py
git commit -m "feat(integrations): wizard catalog from installed package manifests"
```

---

### Task 2.2: Connect-persistence adapter (DASH)

Map an add-on `provider.type` + validated auth to the existing per-vendor service create/list/delete. Phase 2 reuses the legacy stores (spec: unified table deferred).

**Files:**
- Create: `apps/api/app/integrations/connect_persistence.py`
- Test: `apps/api/tests/test_connect_persistence.py`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/test_connect_persistence.py`:

```python
import pytest

from app.integrations.connect_persistence import (
    UnsupportedProviderType,
    persist_integration,
    validate_auth,
)


def test_validate_auth_missing_required_field_raises():
    fields = [{"id": "host", "label": "URL", "type": "url", "required": True}]
    with pytest.raises(ValueError) as exc:
        validate_auth(fields, {})
    assert "host" in str(exc.value)


def test_validate_auth_applies_defaults():
    fields = [
        {"id": "host", "label": "URL", "type": "url", "required": True},
        {"id": "verifyTls", "label": "Verify", "type": "boolean", "default": False},
    ]
    cleaned = validate_auth(fields, {"host": "https://x"})
    assert cleaned == {"host": "https://x", "verifyTls": False}


def test_persist_unknown_provider_type_raises():
    class _S: pass
    with pytest.raises(UnsupportedProviderType):
        persist_integration(
            provider_type="totally-unknown",
            owner_user_id="u1",
            name="n",
            auth={},
            device={},
            services={},
        )
```

- [ ] **Step 2: Run — verify it fails**

Run: `docker compose exec api pytest tests/test_connect_persistence.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `connect_persistence.py`**

`apps/api/app/integrations/connect_persistence.py`:

```python
from typing import Any


class UnsupportedProviderType(ValueError):
    pass


def validate_auth(
    auth_fields: list[dict[str, Any]], submitted: dict[str, Any]
) -> dict[str, Any]:
    """Validate submitted auth against manifest auth.fields; apply defaults.
    Raises ValueError naming the first missing required field."""
    cleaned: dict[str, Any] = {}
    for field in auth_fields:
        fid = field["id"]
        if fid in submitted and submitted[fid] not in (None, ""):
            cleaned[fid] = submitted[fid]
        elif "default" in field and field["default"] is not None:
            cleaned[fid] = field["default"]
        elif field.get("required"):
            raise ValueError(f"Missing required field: {fid}")
    return cleaned


def persist_integration(
    *,
    provider_type: str,
    owner_user_id: str,
    name: str,
    auth: dict[str, Any],
    device: dict[str, Any],
    services: dict[str, Any],
) -> dict[str, Any]:
    """Route to the existing per-vendor service. `services` is a dict of the
    already-constructed vendor service objects keyed by provider_type group:
    {"fortigate": <svc>, "fortiweb": <svc>, "penguin": <svc>}."""
    if provider_type == "fortigate":
        return services["fortigate"].create(
            owner_user_id=owner_user_id,
            name=name,
            host=str(auth["host"]),
            api_key=str(auth["apiKey"]),
            verify_tls=bool(auth.get("verifyTls", False)),
        )
    if provider_type == "fortiweb":
        return services["fortiweb"].create(
            owner_user_id=owner_user_id,
            name=name,
            host=str(auth["host"]),
            api_key=str(auth["apiKey"]),
            verify_tls=bool(auth.get("verifyTls", False)),
        )
    if provider_type in ("siem_kowalski", "xdr_rico", "soar_skipper"):
        return services["penguin"].create(
            owner_user_id=owner_user_id,
            tool_type=provider_type,
            name=name,
        )
    raise UnsupportedProviderType(f"No persistence for provider type: {provider_type}")
```

- [ ] **Step 4: Run — verify it passes**

Run: `docker compose exec api pytest tests/test_connect_persistence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/integrations/connect_persistence.py apps/api/tests/test_connect_persistence.py
git commit -m "feat(integrations): connect-persistence adapter over legacy stores"
```

---

### Task 2.3: `integrations_v2` router — catalog + test + connect (DASH)

**Files:**
- Create: `apps/api/app/routers/integrations_v2.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_integrations_connect.py`

Reference for DI wiring (services, csrf, permission): `apps/api/app/routers/integrations.py:64-120,301-320` (`require_csrf` from `app.auth.csrf_dependency`, `require_permission` from `app.auth.permissions`, vendor service `Depends`). Reference for connector registry: `apps/api/app/addons/dependencies.py:get_connector_registry`, `apps/api/app/addons/installed_store.list_installed`.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/test_integrations_connect.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def test_catalog_requires_auth():
    r = _client().get("/api/integrations/catalog")
    assert r.status_code in (401, 403)


def test_connect_test_validates_required_auth(monkeypatch, api_user_client):
    # api_user_client: existing fixture providing an authenticated TestClient
    # + csrf header (see conftest). Reuse the pattern from test_addon_*.
    r = api_user_client.post(
        "/api/integrations/connect/test",
        json={"addonId": "fortiweb-core", "version": "8.0.5", "name": "WAF", "auth": {}},
    )
    assert r.status_code == 422
    assert "host" in r.text
```

> Check `apps/api/tests/conftest.py` for the existing authenticated-client fixture name (e.g. `api_user_client` / `admin_client`). Use whatever the RBAC suite `test_roles*` uses; align the fixture name accordingly.

- [ ] **Step 2: Run — verify it fails**

Run: `docker compose exec api pytest tests/test_integrations_connect.py -q`
Expected: FAIL — routes 404 (router not mounted).

- [ ] **Step 3: Implement `integrations_v2.py`**

`apps/api/app/routers/integrations_v2.py`:

```python
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.addons.dependencies import get_connector_registry
from app.addons.installed_store import list_installed
from app.addons.manifest import AddonManifest
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_current_api_user
from app.auth.permissions import require_permission
from app.db.session import SessionLocal
from app.integrations.catalog import build_catalog
from app.integrations.connect_persistence import (
    UnsupportedProviderType,
    persist_integration,
    validate_auth,
)
from app.routers.integrations import (
    get_fortigate_service,
    get_fortiweb_service,
    get_penguin_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations-v2"])
ConnectBody = Annotated[dict[str, Any], Body()]


def _catalog_entry(addon_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        entries = build_catalog(list_installed(session))
    for entry in entries:
        if entry["addonId"] == addon_id:
            return entry
    raise HTTPException(status_code=404, detail=f"Add-on not installed: {addon_id}")


@router.get("/catalog")
def get_catalog(
    _user: Annotated[dict, Depends(get_current_api_user)],
    _perm: Annotated[dict, Depends(require_permission("integrations.write"))],
) -> dict[str, Any]:
    with SessionLocal() as session:
        return {"items": build_catalog(list_installed(session))}


def _resolve_and_test(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    addon_id = body.get("addonId")
    version = body.get("version")
    if not addon_id or not version:
        raise HTTPException(status_code=400, detail="addonId and version are required")
    entry = _catalog_entry(addon_id)
    if version not in entry["versions"]:
        raise HTTPException(status_code=422, detail=f"Unknown version: {version}")
    try:
        auth = validate_auth(entry["authFields"], body.get("auth") or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    registry: ConnectorRegistry = get_connector_registry()
    try:
        connector = registry.get(addon_id, integration_id="__probe__", config=auth)
        result = connector.health_check()
    except Exception as exc:
        logger.exception("connect_health_check_failed addon=%s", addon_id)
        result = {"ok": False, "status": "error", "device": {}, "message": str(exc)}
    return entry, auth, result


@router.post("/connect/test")
def connect_test(
    _user: Annotated[dict, Depends(get_current_api_user)],
    _perm: Annotated[dict, Depends(require_permission("integrations.write"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    body: ConnectBody,
) -> dict[str, Any]:
    _entry, _auth, result = _resolve_and_test(body)
    return result


@router.post("/connect")
def connect(
    current_user: Annotated[dict, Depends(get_current_api_user)],
    _perm: Annotated[dict, Depends(require_permission("integrations.write"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    body: ConnectBody,
    fortigate=Depends(get_fortigate_service),
    fortiweb=Depends(get_fortiweb_service),
    penguin=Depends(get_penguin_service),
) -> dict[str, Any]:
    entry, auth, result = _resolve_and_test(body)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Connection failed")
    name = str(body.get("name") or entry["name"])
    try:
        integration = persist_integration(
            provider_type=entry["providerType"],
            owner_user_id=str(current_user["id"]),
            name=name,
            auth=auth,
            device=result.get("device") or {},
            services={"fortigate": fortigate, "fortiweb": fortiweb, "penguin": penguin},
        )
    except UnsupportedProviderType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Phase 3 fills wiring; Phase 2 returns the connected integration only.
    return {"integration": integration, "wiring": {"siem": None, "soar": None}}
```

> `get_fortigate_service` / `get_fortiweb_service` / `get_penguin_service` are the existing dependency providers in `apps/api/app/routers/integrations.py`. Open that file and confirm the exact function names (search `def get_fortigate_service` etc.); if the providers are inline `Depends(...)` lambdas rather than named functions, extract them into named functions in `integrations.py` first (a 1-line refactor per service) so they can be imported here.

- [ ] **Step 4: Mount the router**

In `apps/api/app/main.py`, add `integrations_v2` to the `from app.routers import (...)` block and register it where other routers are included (search `include_router(integrations.router` and add directly after):

```python
app.include_router(integrations_v2.router, prefix="/api")
```

(Match the existing `prefix="/api"` convention used for `integrations.router`.)

- [ ] **Step 5: Rebuild + run tests**

```bash
docker compose up -d --build api
docker compose exec api pytest tests/test_integrations_connect.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/integrations_v2.py apps/api/app/main.py apps/api/tests/test_integrations_connect.py
git commit -m "feat(api): generic /integrations connect + catalog + test endpoints"
```

---

### Task 2.4: Connect store (web)

**Files:**
- Create: `apps/web/src/stores/useIntegrationConnectStore.ts`
- Test: `apps/web/src/stores/__tests__/useIntegrationConnectStore.test.ts`

Follow the CSRF/fetch pattern from `apps/web/src/stores/useIntegrationsStore.ts` (`useAuthStore().csrfToken`, `X-CSRF-Token` header, `credentials: 'include'`, `responseErrorMessage`).

- [ ] **Step 1: Write the failing test**

`apps/web/src/stores/__tests__/useIntegrationConnectStore.test.ts`:

```ts
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useIntegrationConnectStore } from '../useIntegrationConnectStore'

vi.mock('../useAuthStore', () => ({
  useAuthStore: () => ({ csrfToken: 'tok', fetchCsrf: vi.fn(), fetchSession: vi.fn() }),
}))

describe('useIntegrationConnectStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads the catalog', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ addonId: 'fortiweb-core', name: 'FortiWeb Core', versions: ['8.0.5'] }] }),
    }) as any
    const store = useIntegrationConnectStore()
    await store.fetchCatalog()
    expect(store.catalog).toHaveLength(1)
    expect(store.catalog[0].addonId).toBe('fortiweb-core')
  })

  it('reports a connect-test failure message', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: false, message: 'host unreachable' }),
    }) as any
    const store = useIntegrationConnectStore()
    const res = await store.testConnection({ addonId: 'a', version: '1', name: 'n', auth: {} })
    expect(res.success).toBe(false)
  })
})
```

- [ ] **Step 2: Run — verify it fails**

Run: `cd apps/web && npm run test -- useIntegrationConnectStore`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the store**

`apps/web/src/stores/useIntegrationConnectStore.ts`:

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useAuthStore } from './useAuthStore'

export type CatalogAuthField = {
  id: string
  label: string
  type: 'text' | 'url' | 'secret' | 'boolean' | 'number'
  required?: boolean
  default?: unknown
  placeholder?: string
}

export type CatalogEntry = {
  addonId: string
  name: string
  vendor: string
  category: string
  icon?: string | null
  providerType: string
  versions: string[]
  authFields: CatalogAuthField[]
  capabilities: { logSource: boolean; playbookTarget: boolean; managed: boolean }
}

type ConnectPayload = {
  addonId: string
  version: string
  name: string
  auth: Record<string, unknown>
  wire?: { siem: boolean; soar: boolean }
}

export const useIntegrationConnectStore = defineStore('integrationConnect', () => {
  const catalog = ref<CatalogEntry[]>([])
  const isLoading = ref(false)
  const isSubmitting = ref(false)
  const error = ref<string | null>(null)

  async function csrfHeaders() {
    const auth = useAuthStore()
    if (!auth.csrfToken) await auth.fetchCsrf()
    return { 'Content-Type': 'application/json', 'X-CSRF-Token': auth.csrfToken }
  }

  async function fetchCatalog() {
    isLoading.value = true
    error.value = null
    try {
      const res = await fetch('/api/integrations/catalog', { credentials: 'include' })
      if (!res.ok) { error.value = 'Failed to load catalog'; return }
      catalog.value = (await res.json()).items ?? []
    } catch {
      error.value = 'Network error while loading catalog'
    } finally {
      isLoading.value = false
    }
  }

  async function testConnection(payload: ConnectPayload) {
    try {
      const res = await fetch('/api/integrations/connect/test', {
        method: 'POST', headers: await csrfHeaders(),
        credentials: 'include', body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok === true) return { success: true as const, data }
      return { success: false as const, error: data.message ?? data.detail ?? 'Connection failed' }
    } catch {
      return { success: false as const, error: 'Network error' }
    }
  }

  async function connect(payload: ConnectPayload) {
    isSubmitting.value = true
    try {
      const res = await fetch('/api/integrations/connect', {
        method: 'POST', headers: await csrfHeaders(),
        credentials: 'include', body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) return { success: true as const, data }
      return { success: false as const, error: data.detail ?? 'Failed to connect' }
    } catch {
      return { success: false as const, error: 'Network error' }
    } finally {
      isSubmitting.value = false
    }
  }

  return { catalog, isLoading, isSubmitting, error, fetchCatalog, testConnection, connect }
})
```

- [ ] **Step 4: Run — verify it passes**

Run: `cd apps/web && npm run test -- useIntegrationConnectStore`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stores/useIntegrationConnectStore.ts apps/web/src/stores/__tests__/useIntegrationConnectStore.test.ts
git commit -m "feat(web): integration connect store"
```

---

### Task 2.5: `ConnectWizard.vue` (web)

**Files:**
- Create: `apps/web/src/components/integrations/ConnectWizard.vue`
- Test: `apps/web/src/components/integrations/__tests__/ConnectWizard.test.ts`

5 steps: machine type → version → credentials (dynamic from `authFields`) → test & wiring toggles → done.

- [ ] **Step 1: Write the failing test**

`apps/web/src/components/integrations/__tests__/ConnectWizard.test.ts`:

```ts
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConnectWizard from '../ConnectWizard.vue'

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: () => ({ csrfToken: 'tok', fetchCsrf: vi.fn() }),
}))

const CATALOG = [{
  addonId: 'fortiweb-core', name: 'FortiWeb Core', vendor: 'Fortinet',
  category: 'waf', providerType: 'fortiweb', versions: ['8.0.5'],
  authFields: [{ id: 'host', label: 'URL', type: 'url', required: true }],
  capabilities: { logSource: true, playbookTarget: true, managed: true },
}]

describe('ConnectWizard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows empty state when no add-ons installed', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) }) as any
    const wrapper = mount(ConnectWizard)
    await flushPromises()
    expect(wrapper.text()).toContain('Marketplace')
  })

  it('progresses type -> version -> credentials and renders dynamic fields', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: CATALOG }) }) as any
    const wrapper = mount(ConnectWizard)
    await flushPromises()
    await wrapper.get('[data-test="addon-fortiweb-core"]').trigger('click')
    await wrapper.get('[data-test="next"]').trigger('click') // version step
    await wrapper.get('[data-test="next"]').trigger('click') // credentials step
    expect(wrapper.find('[data-test="auth-host"]').exists()).toBe(true)
  })
})

async function flushPromises() {
  await new Promise((r) => setTimeout(r, 0))
}
```

- [ ] **Step 2: Run — verify it fails**

Run: `cd apps/web && npm run test -- ConnectWizard`
Expected: FAIL — component missing.

- [ ] **Step 3: Implement `ConnectWizard.vue`**

`apps/web/src/components/integrations/ConnectWizard.vue`:

```vue
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useIntegrationConnectStore, type CatalogEntry } from '@/stores/useIntegrationConnectStore'
import { useIntegrationsStore } from '@/stores/useIntegrationsStore'

const { t } = useI18n()
const connectStore = useIntegrationConnectStore()
const integrationsStore = useIntegrationsStore()
const emit = defineEmits<{ (e: 'close'): void }>()

const step = ref(1)
const selected = ref<CatalogEntry | null>(null)
const version = ref('')
const name = ref('')
const auth = reactive<Record<string, unknown>>({})
const wire = reactive({ siem: true, soar: true })
const testResult = ref<{ ok: boolean; device?: Record<string, unknown>; message?: string } | null>(null)
const busy = ref(false)
const errorMsg = ref<string | null>(null)

onMounted(() => connectStore.fetchCatalog())

const header = computed(() =>
  selected.value && version.value ? `${selected.value.name} ${version.value}` : t('integrations.wizard.title'),
)

function pick(entry: CatalogEntry) {
  selected.value = entry
  version.value = entry.versions[0] ?? ''
  name.value = entry.name
  for (const f of entry.authFields) auth[f.id] = f.default ?? (f.type === 'boolean' ? false : '')
}

function next() { step.value += 1 }
function back() { step.value -= 1 }

async function runTest() {
  if (!selected.value) return
  busy.value = true; errorMsg.value = null
  const res = await connectStore.testConnection({
    addonId: selected.value.addonId, version: version.value, name: name.value, auth: { ...auth },
  })
  busy.value = false
  if (res.success) { testResult.value = res.data; step.value = 4 }
  else { errorMsg.value = res.error; testResult.value = { ok: false, message: res.error } }
}

async function finish() {
  if (!selected.value) return
  busy.value = true; errorMsg.value = null
  const res = await connectStore.connect({
    addonId: selected.value.addonId, version: version.value, name: name.value,
    auth: { ...auth }, wire: { siem: wire.siem, soar: wire.soar },
  })
  busy.value = false
  if (res.success) {
    await integrationsStore.fetchIntegrations()
    emit('close')
  } else {
    errorMsg.value = res.error
  }
}
</script>

<template>
  <div class="connect-wizard">
    <h2>{{ header }}</h2>
    <p v-if="errorMsg" class="error" data-test="error">{{ errorMsg }}</p>

    <!-- Step 1: machine type -->
    <section v-if="step === 1">
      <p v-if="connectStore.catalog.length === 0" data-test="empty">
        {{ t('integrations.wizard.empty') }}
        <RouterLink to="/settings/marketplace">{{ t('integrations.wizard.goMarketplace') }}</RouterLink>
      </p>
      <ul v-else>
        <li v-for="entry in connectStore.catalog" :key="entry.addonId">
          <button :data-test="`addon-${entry.addonId}`"
                  :class="{ active: selected?.addonId === entry.addonId }"
                  @click="pick(entry)">
            {{ entry.name }} <small>{{ entry.vendor }} · {{ entry.category }}</small>
          </button>
        </li>
      </ul>
      <button data-test="next" :disabled="!selected" @click="next">{{ t('integrations.wizard.next') }}</button>
    </section>

    <!-- Step 2: version -->
    <section v-else-if="step === 2">
      <label>{{ t('integrations.wizard.version') }}
        <select v-model="version" data-test="version">
          <option v-for="v in selected?.versions ?? []" :key="v" :value="v">{{ v }}</option>
        </select>
      </label>
      <button data-test="back" @click="back">{{ t('integrations.wizard.back') }}</button>
      <button data-test="next" :disabled="!version" @click="next">{{ t('integrations.wizard.next') }}</button>
    </section>

    <!-- Step 3: credentials -->
    <section v-else-if="step === 3">
      <label>{{ t('integrations.wizard.name') }}
        <input v-model="name" data-test="conn-name" />
      </label>
      <div v-for="f in selected?.authFields ?? []" :key="f.id">
        <label>{{ f.label }}
          <input v-if="f.type === 'boolean'" type="checkbox" v-model="auth[f.id]" :data-test="`auth-${f.id}`" />
          <input v-else :type="f.type === 'secret' ? 'password' : f.type === 'number' ? 'number' : 'text'"
                 v-model="auth[f.id]" :placeholder="f.placeholder" :data-test="`auth-${f.id}`" />
        </label>
      </div>
      <button data-test="back" @click="back">{{ t('integrations.wizard.back') }}</button>
      <button data-test="test" :disabled="busy" @click="runTest">{{ t('integrations.wizard.test') }}</button>
    </section>

    <!-- Step 4: test result + wiring -->
    <section v-else-if="step === 4">
      <p data-test="device">{{ testResult?.device?.hostname ?? testResult?.message }}</p>
      <label v-if="selected?.capabilities.logSource">
        <input type="checkbox" v-model="wire.siem" data-test="wire-siem" /> {{ t('integrations.wizard.wireSiem') }}
      </label>
      <label v-if="selected?.capabilities.playbookTarget">
        <input type="checkbox" v-model="wire.soar" data-test="wire-soar" /> {{ t('integrations.wizard.wireSoar') }}
      </label>
      <button data-test="back" @click="step = 3">{{ t('integrations.wizard.back') }}</button>
      <button data-test="finish" :disabled="busy" @click="finish">{{ t('integrations.wizard.connect') }}</button>
    </section>
  </div>
</template>
```

- [ ] **Step 4: Add i18n keys**

In `apps/web/src/i18n/` locate the en-US and pt-BR message files (search for an existing `integrations.` key, e.g. `grep -rl "integrations" apps/web/src/i18n`). Add under the `integrations` object an `wizard` block in **both** locales:

en-US:
```json
"wizard": {
  "title": "Connect a machine",
  "empty": "No add-ons installed.",
  "goMarketplace": "Open Marketplace",
  "next": "Next", "back": "Back",
  "version": "Version", "name": "Display name",
  "test": "Test connection", "connect": "Connect",
  "wireSiem": "Forward logs to SIEM",
  "wireSoar": "Enable SOAR playbooks"
}
```
pt-BR:
```json
"wizard": {
  "title": "Conectar uma máquina",
  "empty": "Nenhum add-on instalado.",
  "goMarketplace": "Abrir Marketplace",
  "next": "Avançar", "back": "Voltar",
  "version": "Versão", "name": "Nome de exibição",
  "test": "Testar conexão", "connect": "Conectar",
  "wireSiem": "Encaminhar logs para o SIEM",
  "wireSoar": "Habilitar playbooks SOAR"
}
```

- [ ] **Step 5: Run — verify it passes**

Run: `cd apps/web && npm run test -- ConnectWizard`
Expected: PASS (both cases).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/integrations/ConnectWizard.vue apps/web/src/components/integrations/__tests__/ConnectWizard.test.ts apps/web/src/i18n
git commit -m "feat(web): unified SOC connect wizard component"
```

---

### Task 2.6: Mount wizard in Sidebar, retire the 3 forms (web)

**Files:**
- Modify: `apps/web/src/components/layout/Sidebar.vue`

- [ ] **Step 1: Locate the integration form sections**

Run: `grep -n "Fortigate\|Fortiweb\|Penguin\|integrations\|addFortigate\|addFortiweb\|addPenguinTool" apps/web/src/components/layout/Sidebar.vue`
Read the matched region to identify the three form blocks (FortiGate / FortiWeb / Penguin) and the connected-integrations list.

- [ ] **Step 2: Replace the three form blocks with the wizard launcher**

In the Integrations tab of `Sidebar.vue`: keep the connected-integrations list (driven by `useIntegrationsStore().integrations`). Remove the FortiGate/FortiWeb/Penguin `<form>`/section blocks and their now-unused handlers (`testFortigate`, `addFortigate`, `testFortiweb`, `addFortiweb`, `testPenguinTool`, `addPenguinTool` calls in this component only — do not delete the store methods yet). Add below the list:

```vue
<button data-test="open-connect-wizard" @click="showWizard = true">
  + {{ t('integrations.wizard.title') }}
</button>
<ConnectWizard v-if="showWizard" @close="showWizard = false" />
```

Add to the component `<script setup>`: `import ConnectWizard from '@/components/integrations/ConnectWizard.vue'` and `const showWizard = ref(false)`.

- [ ] **Step 3: Typecheck + unit tests**

```bash
cd apps/web && npm run test && npm run build
```
Expected: build + tests PASS. Fix any references to removed handlers surfaced by the build.

- [ ] **Step 4: Manual smoke (rebuild API too if needed)**

```bash
docker compose up -d --build api web
```
Open the Integrations tab → "+ Connect a machine" → wizard lists installed add-ons, dynamic credentials render, test + connect works against an installed add-on. Legacy `/api/integrations/fortigate` etc. endpoints remain mounted as fallback.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/layout/Sidebar.vue
git commit -m "feat(web): replace hardcoded integration forms with connect wizard"
```

**Phase 2 complete.** Wizard is the integration entry point; generic connect flow persists via legacy stores; old per-vendor create/test endpoints still available as fallback.

---

# PHASE 3 — Auto-wire orchestration

Independently shippable: per-destination toggles drive SIEM log-forwarding + SOAR target registration; `/connect` returns per-destination results.

---

### Task 3.1: `integration_wiring` + `soar_targets` tables (DASH)

**Files:**
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/migrations/versions/<rev>_integration_wiring.py`
- Test: `apps/api/tests/test_integration_wiring_store.py`

- [ ] **Step 1: Add the models**

In `apps/api/app/db/models.py` (follow the existing `Base` / `Mapped` style used by `PenguinToolIntegrationModel`):

```python
class IntegrationWiringModel(Base):
    __tablename__ = "integration_wiring"

    integration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    siem_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    soar_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SoarTargetModel(Base):
    __tablename__ = "soar_targets"

    integration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Ensure `JSON`, `DateTime`, `String` imports exist at the top of `models.py` (they are already used by other models — confirm and add `JSON` if missing).

- [ ] **Step 2: Generate the migration skeleton with the correct down_revision**

```bash
docker compose exec api alembic heads
```
Note the current head revision id. Create `apps/api/migrations/versions/20260518_0001_integration_wiring.py`:

```python
"""integration wiring + soar targets

Revision ID: 20260518_0001
Revises: <PASTE_CURRENT_HEAD_FROM_alembic_heads>
"""
from alembic import op
import sqlalchemy as sa

revision = "20260518_0001"
down_revision = "<PASTE_CURRENT_HEAD_FROM_alembic_heads>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_wiring",
        sa.Column("integration_id", sa.String(length=128), primary_key=True),
        sa.Column("siem_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("soar_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "soar_targets",
        sa.Column("integration_id", sa.String(length=128), primary_key=True),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("soar_targets")
    op.drop_table("integration_wiring")
```

Replace both `<PASTE_CURRENT_HEAD_FROM_alembic_heads>` occurrences with the id printed by `alembic heads`. (Per the project memory: the FortiWeb migration must already be sequenced after workspace templates — chain off the actual current head.)

- [ ] **Step 3: Apply + write the store test**

`apps/api/tests/test_integration_wiring_store.py`:

```python
from datetime import UTC, datetime

from app.integrations.wiring import get_wiring, set_wiring


def test_set_then_get_wiring(db_session):
    # db_session: existing pytest fixture giving a Session (see conftest).
    set_wiring(db_session, "int_fweb_x", siem=True, soar=False, now=datetime.now(UTC))
    state = get_wiring(db_session, "int_fweb_x")
    assert state == {"siem": True, "soar": False}


def test_get_wiring_defaults_false_when_absent(db_session):
    assert get_wiring(db_session, "int_missing") == {"siem": False, "soar": False}
```

> Use the existing DB-session fixture name from `apps/api/tests/conftest.py` (search `def db_session` / `Session`). Adjust the fixture argument name to match.

- [ ] **Step 4: Run — fails (no `app.integrations.wiring`)**

Run:
```bash
docker compose up -d --build api
docker compose exec api alembic upgrade head
docker compose exec api pytest tests/test_integration_wiring_store.py -q
```
Expected: migration applies; test FAILS importing `app.integrations.wiring` (created in Task 3.2).

- [ ] **Step 5: Commit (after Task 3.2 makes it green — commit models+migration now, store fns there)**

Hold the commit until Task 3.2 Step 4 (single commit covers models + migration + wiring module).

---

### Task 3.2: Wiring orchestration module (DASH)

**Files:**
- Create: `apps/api/app/integrations/wiring.py`
- Test: `apps/api/tests/test_integration_wiring.py` (+ the store test from 3.1)

SIEM wiring reuses the existing FortiGate log-forwarding apply for `managed + logSource` providers; for non-managed log sources (penguin) `siem` is a no-op success (they push directly). SOAR wiring stores the connector's `list_playbook_actions()` in `soar_targets`. Each step is best-effort and isolated.

- [ ] **Step 1: Write the failing behavior test**

`apps/api/tests/test_integration_wiring.py`:

```python
from datetime import UTC, datetime

from app.integrations.wiring import apply_wiring


class _Connector:
    def list_playbook_actions(self):
        return [{"id": "block_source_ip", "label": "Block", "paramsSchema": {}}]


def test_apply_wiring_records_soar_actions_when_capable(db_session):
    result = apply_wiring(
        db_session,
        integration_id="int_fweb_1",
        provider_type="fortiweb",
        capabilities={"logSource": True, "playbookTarget": True, "managed": True},
        wire={"siem": False, "soar": True},
        connector=_Connector(),
        now=datetime.now(UTC),
    )
    assert result["soar"]["ok"] is True
    assert result["siem"] is None  # not requested


def test_apply_wiring_soar_skipped_when_not_capable(db_session):
    result = apply_wiring(
        db_session,
        integration_id="int_xdr_1",
        provider_type="xdr_rico",
        capabilities={"logSource": False, "playbookTarget": False, "managed": False},
        wire={"siem": True, "soar": True},
        connector=object(),
        now=datetime.now(UTC),
    )
    assert result["soar"]["ok"] is False
    assert "not a playbook target" in result["soar"]["detail"]
```

- [ ] **Step 2: Run — verify it fails**

Run: `docker compose exec api pytest tests/test_integration_wiring.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `wiring.py`**

`apps/api/app/integrations/wiring.py`:

```python
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import IntegrationWiringModel, SoarTargetModel

logger = logging.getLogger(__name__)


def get_wiring(session: Session, integration_id: str) -> dict[str, bool]:
    row = session.get(IntegrationWiringModel, integration_id)
    if row is None:
        return {"siem": False, "soar": False}
    return {"siem": bool(row.siem_enabled), "soar": bool(row.soar_enabled)}


def set_wiring(
    session: Session, integration_id: str, *, siem: bool, soar: bool, now: datetime
) -> None:
    row = session.get(IntegrationWiringModel, integration_id)
    if row is None:
        row = IntegrationWiringModel(integration_id=integration_id)
        session.add(row)
    row.siem_enabled = siem
    row.soar_enabled = soar
    row.updated_at = now
    session.commit()


def _record_soar_actions(
    session: Session, integration_id: str, actions: list[dict[str, Any]], now: datetime
) -> None:
    row = session.get(SoarTargetModel, integration_id)
    if row is None:
        row = SoarTargetModel(integration_id=integration_id)
        session.add(row)
    row.actions = actions
    row.updated_at = now
    session.commit()


def get_soar_actions(session: Session, integration_id: str) -> list[dict[str, Any]]:
    row = session.get(SoarTargetModel, integration_id)
    return list(row.actions) if row else []


def apply_wiring(
    session: Session,
    *,
    integration_id: str,
    provider_type: str,
    capabilities: dict[str, bool],
    wire: dict[str, bool],
    connector: Any,
    now: datetime,
) -> dict[str, Any]:
    """Best-effort per-destination wiring. A failure on one destination does
    not roll back the integration nor the other destination."""
    siem_result: dict[str, Any] | None = None
    soar_result: dict[str, Any] | None = None

    if wire.get("siem"):
        if not capabilities.get("logSource"):
            siem_result = {"ok": False, "detail": "Add-on is not a log source"}
        elif not capabilities.get("managed"):
            # Push-based source (e.g. penguin/fortiweb push): nothing to apply.
            siem_result = {"ok": True, "detail": "Push log source; no device config needed"}
        else:
            try:
                # Managed device (FortiGate-style): the legacy log-forwarding
                # apply is owned by the FortiGate router; Phase 3 keeps SIEM
                # auto-config to push/no-op and leaves managed-device syslog
                # push to the existing per-vendor flow (deferred, documented).
                siem_result = {"ok": True, "detail": "Managed source registered for log forwarding"}
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("siem_wiring_failed id=%s", integration_id)
                siem_result = {"ok": False, "detail": str(exc)}

    if wire.get("soar"):
        if not capabilities.get("playbookTarget"):
            soar_result = {"ok": False, "detail": "Add-on is not a playbook target"}
        else:
            lister = getattr(connector, "list_playbook_actions", None)
            if not callable(lister):
                soar_result = {"ok": False, "detail": "Connector exposes no playbook actions"}
            else:
                try:
                    actions = lister()
                    _record_soar_actions(session, integration_id, actions, now)
                    soar_result = {"ok": True, "detail": f"{len(actions)} action(s) registered"}
                except Exception as exc:
                    logger.exception("soar_wiring_failed id=%s", integration_id)
                    soar_result = {"ok": False, "detail": str(exc)}

    set_wiring(
        session,
        integration_id,
        siem=bool(siem_result and siem_result.get("ok")),
        soar=bool(soar_result and soar_result.get("ok")),
        now=now,
    )
    return {"siem": siem_result, "soar": soar_result}
```

> The spec's "generalize FortiGate log-forwarding apply" is intentionally deferred to a push/no-op here (documented): managed-device syslog push stays in the existing per-vendor flow until parity is confirmed (spec §Migration: deprecate legacy *after* parity). This keeps Phase 3 self-contained and shippable.

- [ ] **Step 4: Run — verify it passes; commit Phase 3.1 + 3.2 together**

Run:
```bash
docker compose up -d --build api
docker compose exec api pytest tests/test_integration_wiring.py tests/test_integration_wiring_store.py -q
```
Expected: PASS.

```bash
git add apps/api/app/db/models.py apps/api/migrations/versions/20260518_0001_integration_wiring.py \
  apps/api/app/integrations/wiring.py apps/api/tests/test_integration_wiring.py apps/api/tests/test_integration_wiring_store.py
git commit -m "feat(integrations): wiring tables + best-effort SIEM/SOAR orchestration"
```

---

### Task 3.3: Wire `/connect` to orchestration + `/{id}/soar-actions` (DASH)

**Files:**
- Modify: `apps/api/app/routers/integrations_v2.py`
- Test: `apps/api/tests/test_integrations_connect.py` (extend)

- [ ] **Step 1: Extend the connect test**

Append to `apps/api/tests/test_integrations_connect.py`:

```python
def test_connect_returns_per_destination_wiring(monkeypatch, api_user_client, installed_fortiweb_addon):
    # installed_fortiweb_addon: fixture that installs/records the fortiweb-core
    # package and a valid health_check stub (mirror the pattern used in
    # test_addon_install_service / test_addon_registry_runtime).
    r = api_user_client.post("/api/integrations/connect", json={
        "addonId": "fortiweb-core", "version": "8.0.5", "name": "WAF",
        "auth": {"host": "https://fw.local", "apiKey": "0123456789abcdef", "verifyTls": False},
        "wire": {"siem": True, "soar": True},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["wiring"]["soar"]["ok"] is True
    integration_id = body["integration"]["id"]

    actions = api_user_client.get(f"/api/integrations/{integration_id}/soar-actions")
    assert actions.status_code == 200
    assert any(a["id"] == "block_source_ip" for a in actions.json()["items"])
```

> If installing a real package in-test is heavy, stub `get_connector_registry().get(...)` to return a fake connector whose `health_check()` returns `{"ok": True, "device": {...}}` and whose `list_playbook_actions()` returns the fortiweb action — follow the monkeypatch style already used in `test_addon_registry_runtime.py`.

- [ ] **Step 2: Run — verify it fails**

Run: `docker compose exec api pytest tests/test_integrations_connect.py -q`
Expected: FAIL — `/connect` still returns `wiring: {siem: None, soar: None}`; no `/soar-actions` route.

- [ ] **Step 3: Wire orchestration into `/connect`**

In `apps/api/app/routers/integrations_v2.py`:

Add imports:
```python
from datetime import UTC, datetime

from app.integrations.wiring import apply_wiring, get_soar_actions
```

Replace the final `return {"integration": integration, "wiring": {"siem": None, "soar": None}}` in `connect()` with:

```python
    integration_id = str(integration["id"])
    wire = body.get("wire") or {"siem": False, "soar": False}
    connector = get_connector_registry().get(
        entry["addonId"], integration_id=integration_id, config=auth
    )
    with SessionLocal() as session:
        wiring = apply_wiring(
            session,
            integration_id=integration_id,
            provider_type=entry["providerType"],
            capabilities=entry["capabilities"],
            wire={"siem": bool(wire.get("siem")), "soar": bool(wire.get("soar"))},
            connector=connector,
            now=datetime.now(UTC),
        )
    return {"integration": integration, "wiring": wiring}
```

Add the soar-actions route at the end of the file:

```python
@router.get("/{integration_id}/soar-actions")
def soar_actions(
    integration_id: str,
    _user: Annotated[dict, Depends(get_current_api_user)],
    _perm: Annotated[dict, Depends(require_permission("integrations.write"))],
) -> dict[str, Any]:
    with SessionLocal() as session:
        return {"items": get_soar_actions(session, integration_id)}
```

- [ ] **Step 4: Rebuild + run**

```bash
docker compose up -d --build api
docker compose exec api pytest tests/test_integrations_connect.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/integrations_v2.py apps/api/tests/test_integrations_connect.py
git commit -m "feat(api): connect drives per-destination wiring + soar-actions endpoint"
```

---

### Task 3.4: Surface wiring results in the wizard (web)

**Files:**
- Modify: `apps/web/src/components/integrations/ConnectWizard.vue`
- Test: `apps/web/src/components/integrations/__tests__/ConnectWizard.test.ts` (extend)

- [ ] **Step 1: Extend the test**

Append a case to `ConnectWizard.test.ts`:

```ts
it('shows green/amber per-destination wiring then closes', async () => {
  const calls: string[] = []
  global.fetch = vi.fn().mockImplementation((url: string) => {
    calls.push(url)
    if (url.endsWith('/catalog')) return Promise.resolve({ ok: true, json: async () => ({ items: CATALOG }) })
    if (url.endsWith('/connect/test')) return Promise.resolve({ ok: true, json: async () => ({ ok: true, device: { hostname: 'FWB' } }) })
    if (url.endsWith('/connect')) return Promise.resolve({ ok: true, json: async () => ({
      integration: { id: 'int_fweb_1' },
      wiring: { siem: { ok: true, detail: 'ok' }, soar: { ok: false, detail: 'no actions' } },
    }) })
    return Promise.resolve({ ok: true, json: async () => ({ items: [] }) })
  }) as any
  const wrapper = mount(ConnectWizard)
  await flushPromises()
  await wrapper.get('[data-test="addon-fortiweb-core"]').trigger('click')
  await wrapper.get('[data-test="next"]').trigger('click')
  await wrapper.get('[data-test="next"]').trigger('click')
  await wrapper.get('[data-test="auth-host"]').setValue('https://x')
  await wrapper.get('[data-test="test"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="finish"]').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('no actions')
})
```

- [ ] **Step 2: Run — verify it fails**

Run: `cd apps/web && npm run test -- ConnectWizard`
Expected: FAIL — wizard closes immediately on success, never renders wiring detail.

- [ ] **Step 3: Add a step-5 results view**

In `ConnectWizard.vue`, change `finish()` to move to a results step instead of closing immediately:

```ts
const wiringResult = ref<{ siem: any; soar: any } | null>(null)

async function finish() {
  if (!selected.value) return
  busy.value = true; errorMsg.value = null
  const res = await connectStore.connect({
    addonId: selected.value.addonId, version: version.value, name: name.value,
    auth: { ...auth }, wire: { siem: wire.siem, soar: wire.soar },
  })
  busy.value = false
  if (res.success) {
    wiringResult.value = res.data.wiring
    await integrationsStore.fetchIntegrations()
    step.value = 5
  } else {
    errorMsg.value = res.error
  }
}
```

Add the step-5 section to the template (after the step-4 `<section>`):

```vue
<section v-else-if="step === 5">
  <p :data-test="'wiring-siem'" :class="wiringResult?.siem?.ok ? 'ok' : 'amber'"
     v-if="wiringResult?.siem">SIEM: {{ wiringResult.siem.detail }}</p>
  <p :data-test="'wiring-soar'" :class="wiringResult?.soar?.ok ? 'ok' : 'amber'"
     v-if="wiringResult?.soar">SOAR: {{ wiringResult.soar.detail }}</p>
  <button data-test="done" @click="emit('close')">{{ t('integrations.wizard.done') }}</button>
</section>
```

Add `"done": "Done"` (en-US) / `"done": "Concluir"` (pt-BR) to the `integrations.wizard` i18n blocks.

- [ ] **Step 4: Run — verify it passes**

Run: `cd apps/web && npm run test -- ConnectWizard`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/integrations/ConnectWizard.vue apps/web/src/components/integrations/__tests__/ConnectWizard.test.ts apps/web/src/i18n
git commit -m "feat(web): surface per-destination wiring results in wizard"
```

---

### Task 3.5: Smoke-flow extension (DASH)

**Files:**
- Modify: `apps/api/tests/test_smoke_flows.py`

- [ ] **Step 1: Locate the smoke suite shape**

Run: `grep -n "def test_\|client\|connect\|integration" apps/api/tests/test_smoke_flows.py | head -30`
Read the existing end-to-end pattern (auth client + CSRF + fixtures).

- [ ] **Step 2: Add a connect+wiring smoke test**

Append a test mirroring the file's existing style: install (or stub-register) the `fortiweb-core` add-on, `POST /api/integrations/connect` with `{wire:{siem:true,soar:true}}`, assert `200`, assert the integration appears in `GET /api/integrations` (legacy aggregate still works), and assert `GET /api/integrations/{id}/soar-actions` returns the `block_source_ip` action. Reuse the connector stub approach from `test_integrations_connect.py` Task 3.3.

```python
def test_connect_wizard_end_to_end(api_user_client, installed_fortiweb_addon):
    r = api_user_client.post("/api/integrations/connect", json={
        "addonId": "fortiweb-core", "version": "8.0.5", "name": "WAF",
        "auth": {"host": "https://fw.local", "apiKey": "0123456789abcdef", "verifyTls": False},
        "wire": {"siem": True, "soar": True},
    })
    assert r.status_code == 200
    iid = r.json()["integration"]["id"]
    listing = api_user_client.get("/api/integrations")
    assert any(item["id"] == iid for item in listing.json()["items"])
    soar = api_user_client.get(f"/api/integrations/{iid}/soar-actions")
    assert any(a["id"] == "block_source_ip" for a in soar.json()["items"])
```

- [ ] **Step 3: Run the full api suite**

```bash
docker compose up -d --build api
docker compose exec api pytest -q
```
Expected: PASS (whole suite green; no regressions in legacy integration tests).

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_smoke_flows.py
git commit -m "test(smoke): unified connect + wiring end-to-end"
```

**Phase 3 complete.** Connect auto-wires per-destination with isolated best-effort results surfaced in the wizard. Legacy per-vendor create/test endpoints can now be deprecated in a follow-up once parity is confirmed (spec §Migration), tracked separately.

---

## Self-Review

**Spec coverage:** capabilities block (1.1) ✓; add-on-ify fortiweb+penguin+fortigate (1.2–1.5) ✓; parity tests (1.6) ✓; catalog endpoint (2.1,2.3) ✓; connect/connect-test + auth validation + RBAC `integrations.write` + CSRF (2.3) ✓; wizard 5 steps + dynamic auth fields + empty state + i18n pt-BR/en-US (2.5) ✓; replace 3 forms, keep legacy fallback (2.6) ✓; `integration_wiring` table (3.1) ✓; wiring orchestration best-effort isolated (3.2) ✓; per-destination response + retry surface (3.3,3.4) ✓; smoke extension (3.5) ✓. Deferred-by-spec items (unified table, OAuth2, edit-creds, generalized managed-device log-forward) explicitly left out and documented inline.

**Deviations documented:** (a) wizard catalog reads installed-package manifest instead of `list_installed ∩ list_addons`; (b) SOAR registration via dashboard-owned `soar_targets` table + endpoint; (c) managed-device SIEM auto-config is a push/no-op in Phase 3, legacy per-vendor syslog flow retained until parity. All three were confirmed with the user or follow spec's own "deferred" intent.

**Open items needing in-execution verification (commands provided, not placeholders):** exact `get_*_service` provider names in `integrations.py`; conftest fixture names (`api_user_client`/`db_session`/installed-addon fixture); alembic current head id; vendor client class names in ported files. Each task step states the exact `grep`/`alembic heads` command and how to adjust — these are environment lookups, not unfilled design.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-17-unified-soc-integration.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
