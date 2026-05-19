# FortiAnalyzer Core Add-on Design

Date: 2026-05-19

## Goal

Create a first FortiAnalyzer marketplace package in
`ping-wins/fortidashboard-addons` so FortiDashboard can list, install, and
probe an on-prem FortiAnalyzer integration through the existing add-on loader.
This first version is deliberately read-only and lab-unvalidated.

## Context

FortiDashboard marketplace add-ons are self-contained packages: manifest,
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

Add this package to `ping-wins/fortidashboard-addons`:

```txt
fortianalyzer-core/1.0.0/
  addon.json
  README.md
  connector/
    __init__.py
    fortianalyzer_client.py
```

Update root `catalog.json` with:

- `id`: `fortianalyzer-core`
- `name`: `FortiAnalyzer Core`
- `vendor`: `Fortinet`
- `category`: `siem`
- `latestVersion`: `1.0.0`
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
- `capabilities.playbookTarget`: `false`
- `capabilities.managed`: `true`

Routes document the read-only JSON-RPC health probe:

- `POST /jsonrpc`
- JSON-RPC request target `url: "/sys/status"`

Widgets and SIEM event types stay empty for `1.0.0` unless the existing
dashboard already has FortiAnalyzer-specific widget IDs. This avoids presenting
unverified log extraction as a real product path.

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

`get_widget_data()` returns a ready empty payload:

```json
{"status": "ready", "data": {}, "meta": {"source": "fortianalyzer"}}
```

`ingest_events()` returns an empty list in `1.0.0`. Pulling FortiAnalyzer logs
or incidents is deferred until a real appliance/lab can validate endpoint
paths, ADOM handling, filters, paging, and payload normalization.

## Error Handling And Security

- Never log or return the API key.
- Use `Authorization: Bearer <apiKey>`.
- Trim the host URL and reject empty API keys before making a request.
- Treat HTTP 401 and 403 as credentials or trusted-host/profile failures.
- Treat HTTP 404 as host/API path/firmware mismatch.
- Include short response excerpts only for diagnostics, never secrets.
- All behavior is read-only; no FortiAnalyzer configuration changes are
  included in this package.

## Testing

Because no FortiAnalyzer appliance is available, tests use `httpx.MockTransport`
or direct monkeypatching:

- Missing host returns `missing_host`.
- Successful `/jsonrpc` response normalizes device metadata.
- HTTP 401/403 returns a clear disconnected result.
- JSON-RPC error status returns a disconnected result.
- `get_widget_data()` and `ingest_events()` return stable empty shapes.

Manual verification after publication:

1. Install `fortianalyzer-core@1.0.0` from the marketplace.
2. Connect with a read-only FortiAnalyzer REST API Admin key.
3. Confirm health check succeeds.
4. Confirm no widgets or SIEM ingestion are advertised beyond the tested
   health probe.

## Non-Goals

- Session-based username/password login.
- FortiAnalyzer Cloud OAuth/FortiCloud authentication.
- Live log/event ingestion.
- FortiAnalyzer policy/configuration writes.
- Playbook actions.
- Dashboard-side provider persistence changes beyond whatever the existing
  generic integration flow already supports.

## Open Risks

- The `/sys/status` JSON-RPC probe follows the FortiManager/FortiAnalyzer
  JSON-RPC convention, but this implementation cannot be appliance-tested in
  the current environment.
- FortiDashboard may need a future `provider.type = "fortianalyzer"` persistence
  path if the generic connect flow does not yet accept that provider type.
- Real log ingestion will need a separate design once ADOM, log type, paging,
  and normalization requirements are known.
