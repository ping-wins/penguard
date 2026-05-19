# FortiAnalyzer Core Add-on Design

Date: 2026-05-19

## Goal

Create a beta FortiAnalyzer marketplace package in
`ping-wins/penguard-addons` so Penguard can list, install, and
preview an on-prem FortiAnalyzer integration through the existing add-on
loader. This beta version is deliberately read-only and exists mainly so
FortiAnalyzer appears in the marketplace while appliance validation is pending.

## Context

Penguard marketplace add-ons are self-contained packages: manifest,
Python connector code, and optional fixtures. New vendor packages belong in the
registry repo, not in this monorepo's transitional `addons/` directory.

Fortinet documents FortiAnalyzer JSON API setup through administrators with
JSON API access. A REST API Admin can generate a predefined permanent API key,
and that key is sent with bearer authentication; trusted hosts and appropriate
admin-profile permissions are required.

Reference:

- Fortinet Document Library, FortiAnalyzer 7.6.5 Administration Guide:
  "Creating administrators for the FortiAnalyzer API"
  (`https://docs.fortinet.com/document/fortianalyzer/7.6.5/administration-guide/797124/creating-administrators-for-the-fortianalyzer-api`)

## Package Scope

Add this package to `ping-wins/penguard-addons`:

```txt
fortianalyzer-core/0.1.0-beta.1/
  addon.json
  README.md
  connector/
    __init__.py
    fortianalyzer_client.py
```

Update root `catalog.json` with:

- `id`: `fortianalyzer-core`
- `name`: `FortiAnalyzer Core Beta`
- `vendor`: `Fortinet`
- `category`: `siem`
- `description`: SIEM analytics beta with health-probe scaffold, preview
  widgets and draft-only analyst playbook actions
- `latestVersion`: `0.1.0-beta.1`
- `tagTemplate`: `fortianalyzer-core-v{version}`

## Manifest

The manifest uses the current `AddonManifest` schema without new fields.

Authentication fields:

- `host`, required URL, for example `https://fortianalyzer.example.local`
- `apiKey`, required secret
- `verifyTls`, boolean, default `false`

Provider and capabilities:

- `provider.type`: `fortianalyzer`
- `provider.auth.kind`: `apiKey`
- `capabilities.logSource`: `true`
- `capabilities.playbookTarget`: `true`
- `capabilities.managed`: `true`

Routes document the read-only JSON-RPC health probe:

- `POST /jsonrpc`
- JSON-RPC request target `url: "/sys/status"`

Widgets are advertised for marketplace visibility and return preview payloads
only:

- `fortianalyzer-health-preview`
- `fortianalyzer-adom-log-posture`
- `fortianalyzer-top-event-types`
- `fortianalyzer-ingestion-readiness`

Every widget response includes `mode: "preview"`, `beta: true` and
`applianceValidated: false`. SIEM event types stay empty because live log
ingestion is not validated.

## Connector Behavior

The connector must not import dashboard modules. It duck-types the existing
contract:

```python
health_check() -> dict
get_widget_data(req) -> dict
ingest_events(since) -> list[dict]
close() -> None
```

`health_check()`:

1. Requires `host`; missing host returns
   `{"ok": false, "status": "missing_host", ...}`.
2. Creates a `FortiAnalyzerApiClient` with bearer API key and TLS setting.
3. Sends `POST /jsonrpc` with a read-only JSON-RPC `get` request for
   `/sys/status`.
4. Returns `ok: true`, `status: "connected"`, and normalized device metadata
   (`vendor`, `product`, `hostname`, `model`, `version`, `serial`) when the
   response is successful.
5. Returns `ok: false`, `status: "disconnected"`, and a sanitized message for
   HTTP, network, non-JSON, and JSON-RPC errors.

`get_widget_data()` returns preview payloads:

```json
{
  "status": "preview",
  "data": {
    "title": "FortiAnalyzer health preview",
    "applianceValidated": false,
    "validationRequired": true
  },
  "meta": {
    "source": "fortianalyzer",
    "mode": "preview",
    "applianceValidated": false,
    "beta": true
  }
}
```

`ingest_events()` returns an empty list in `0.1.0-beta.1`. Pulling
FortiAnalyzer logs or incidents is deferred until a real appliance/lab can
validate endpoint paths, ADOM handling, filters, paging, and payload
normalization.

`list_playbook_actions()` exposes one draft-only action:

- `review_fortianalyzer_signal`

`run_playbook_action()` never changes FortiAnalyzer state. It returns
`dryRun: true`, `status: "drafted"`, `applianceValidated: false`, sanitized
params and analyst next steps for manual validation.

## Error Handling And Security

- Never log or return the API key.
- Use `Authorization: Bearer <apiKey>`.
- Trim the host URL and reject empty API keys before making a request.
- Treat HTTP 401 and 403 as credentials or trusted-host/profile failures.
- Treat HTTP 404 as host/API path/firmware mismatch.
- Include short response excerpts only for diagnostics, never secrets.
- All behavior is read-only; no FortiAnalyzer configuration changes or
  containment actions are included in this package.
- Do not report credentials as validated unless the JSON-RPC health probe
  actually succeeds against a FortiAnalyzer appliance.

## Testing

Because no FortiAnalyzer appliance is available, tests use `httpx.MockTransport`
or direct monkeypatching:

- Missing host returns `missing_host`.
- Successful `/jsonrpc` response normalizes device metadata.
- HTTP 401/403 returns a clear disconnected result.
- JSON-RPC error status returns a disconnected result.
- Manifest advertises the beta widgets and draft-only playbook capability.
- `get_widget_data()` returns preview payloads marked unvalidated.
- `run_playbook_action()` returns a dry-run draft and redacts secret params.
- `ingest_events()` returns a stable empty list.

Manual verification after publication:

1. Install `fortianalyzer-core@0.1.0-beta.1` from the marketplace.
2. Connect with a read-only FortiAnalyzer REST API Admin key.
3. Confirm health check succeeds.
4. Confirm widgets appear as beta preview data and do not claim live appliance
   validation.
5. Confirm the playbook action is draft-only and dry-run.

## Non-Goals

- Session-based username/password login.
- FortiAnalyzer Cloud OAuth/FortiCloud authentication.
- Live log/event ingestion.
- FortiAnalyzer policy/configuration writes.
- Live playbook actions or containment.
- Dashboard-side provider persistence changes beyond whatever the existing
  generic integration flow already supports.

## Open Risks

- The `/sys/status` JSON-RPC probe follows the FortiManager/FortiAnalyzer
  JSON-RPC convention, but this implementation cannot be appliance-tested in
  the current environment.
- Penguard may need a future `provider.type = "fortianalyzer"` persistence
  path if the generic connect flow does not yet accept that provider type.
- Real log ingestion will need a separate design once ADOM, log type, paging,
  and normalization requirements are known.
