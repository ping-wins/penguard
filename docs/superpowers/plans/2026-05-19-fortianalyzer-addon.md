# FortiAnalyzer Core Add-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a read-only `fortianalyzer-core` marketplace add-on package with API-key health probing.

**Architecture:** The package lives in the external registry checkout at `/home/guest/penguard-addons`. It follows existing add-on package patterns: manifest + connector package + pytest tests, with no imports from Penguard internals. The connector uses FortiAnalyzer JSON-RPC over `POST /jsonrpc` with bearer API-key auth and exposes stable empty widget/event methods until a real FortiAnalyzer lab validates ingestion.

**Tech Stack:** Python 3.12+, stdlib, `httpx`, `pytest`, GitHub registry repo `ping-wins/penguard-addons`.

---

### Task 1: Add FortiAnalyzer Connector Tests

**Files:**
- Create: `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/tests/test_connector.py`

- [ ] **Step 1: Create package test directory**

Run:

```bash
mkdir -p /home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/tests
```

- [ ] **Step 2: Write failing connector tests**

Create `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/tests/test_connector.py` with tests for:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def load_connector_module():
    entry = PACKAGE_ROOT / "connector" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "fortianalyzer_connector_test",
        entry,
        submodule_search_locations=[str(entry.parent)],
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_missing_host_is_graceful():
    module = load_connector_module()
    connector = module.get_connector({"host": "", "apiKey": "secret"})

    result = connector.health_check()

    assert result["ok"] is False
    assert result["status"] == "missing_host"
    assert result["device"] == {}
    assert "host" in result["message"].lower()


def test_health_check_posts_jsonrpc_status_and_normalizes_device():
    module = load_connector_module()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/jsonrpc"
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.json() == {
            "id": 1,
            "method": "get",
            "params": [{"url": "/sys/status"}],
        }
        return httpx.Response(
            200,
            json={
                "id": 1,
                "result": [
                    {
                        "status": {"code": 0, "message": "OK"},
                        "data": {
                            "hostname": "faza-lab",
                            "platform_str": "FortiAnalyzer-VM64",
                            "version": "v7.6.5",
                            "serial": "FAZVMTEST123",
                        },
                    }
                ],
            },
        )

    client = module.FortiAnalyzerApiClient(
        host="https://faz.local",
        api_key="secret",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )
    connector = module.FortiAnalyzerConnector(
        {"host": "https://faz.local", "apiKey": "secret", "verifyTls": False},
        client=client,
    )

    result = connector.health_check()

    assert len(requests) == 1
    assert result["ok"] is True
    assert result["status"] == "connected"
    assert result["device"] == {
        "vendor": "Fortinet",
        "product": "FortiAnalyzer",
        "hostname": "faza-lab",
        "model": "FortiAnalyzer-VM64",
        "version": "v7.6.5",
        "serial": "FAZVMTEST123",
    }


def test_http_auth_failure_is_sanitized():
    module = load_connector_module()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "trusted host check failed"})

    client = module.FortiAnalyzerApiClient(
        host="https://faz.local",
        api_key="secret",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )
    connector = module.FortiAnalyzerConnector(
        {"host": "https://faz.local", "apiKey": "secret", "verifyTls": False},
        client=client,
    )

    result = connector.health_check()

    assert result["ok"] is False
    assert result["status"] == "disconnected"
    assert "trusted host" in result["message"].lower()
    assert "secret" not in result["message"]


def test_jsonrpc_error_status_is_disconnected():
    module = load_connector_module()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 1,
                "result": [
                    {
                        "status": {
                            "code": -11,
                            "message": "No permission for the resource",
                        }
                    }
                ],
            },
        )

    client = module.FortiAnalyzerApiClient(
        host="https://faz.local",
        api_key="secret",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )
    connector = module.FortiAnalyzerConnector(
        {"host": "https://faz.local", "apiKey": "secret", "verifyTls": False},
        client=client,
    )

    result = connector.health_check()

    assert result["ok"] is False
    assert result["status"] == "disconnected"
    assert "permission" in result["message"].lower()


def test_widget_and_ingest_shapes_are_stable_empty_payloads():
    module = load_connector_module()
    connector = module.get_connector(
        {"host": "https://faz.local", "apiKey": "secret", "verifyTls": False}
    )

    assert connector.get_widget_data({"widget_id": "x"}) == {
        "status": "ready",
        "data": {},
        "meta": {"source": "fortianalyzer"},
    }
    assert connector.ingest_events(None) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
cd /home/guest/penguard-addons
python -m pytest fortianalyzer-core/0.1.0-beta.1/tests/test_connector.py -q
```

Expected: FAIL because `connector/__init__.py` does not exist yet.

### Task 2: Implement FortiAnalyzer Connector Package

**Files:**
- Create: `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/connector/__init__.py`
- Create: `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/connector/fortianalyzer_client.py`
- Create: `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/addon.json`
- Create: `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/README.md`
- Modify: `/home/guest/penguard-addons/catalog.json`

- [ ] **Step 1: Create package directories**

Run:

```bash
mkdir -p /home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/connector
```

- [ ] **Step 2: Implement the client and connector**

Create the two connector files with:

```python
# connector/fortianalyzer_client.py
from __future__ import annotations

import json as jsonlib
from typing import Any

import httpx


class FortiAnalyzerApiError(RuntimeError):
    pass


class FortiAnalyzerApiClient:
    def __init__(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        self.host = host.rstrip("/")
        self.api_key = api_key.strip()
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def get_system_status(self) -> dict[str, Any]:
        payload = self._jsonrpc("get", [{"url": "/sys/status"}])
        result = _first_result(payload)
        status = result.get("status")
        if isinstance(status, dict) and int(status.get("code", 0) or 0) != 0:
            raise FortiAnalyzerApiError(str(status.get("message") or "FortiAnalyzer JSON-RPC error"))
        data = result.get("data")
        if isinstance(data, dict):
            return data
        return result

    def _jsonrpc(self, method: str, params: list[dict[str, Any]]) -> dict[str, Any]:
        request_payload = {"id": 1, "method": method, "params": params}
        try:
            with httpx.Client(
                base_url=self.host,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                verify=self.verify_tls,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post("/jsonrpc", json=request_payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FortiAnalyzerApiError(_http_status_error_message(exc.response)) from exc
        except httpx.RequestError as exc:
            raise FortiAnalyzerApiError(f"FortiAnalyzer API request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise FortiAnalyzerApiError("FortiAnalyzer API returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise FortiAnalyzerApiError("FortiAnalyzer JSON-RPC response was not an object")
        if payload.get("error"):
            raise FortiAnalyzerApiError(_json_excerpt(payload["error"]))
        return payload


def _first_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0]
    if isinstance(result, dict):
        return result
    raise FortiAnalyzerApiError("FortiAnalyzer JSON-RPC response did not include a result object")


def _http_status_error_message(response: httpx.Response) -> str:
    if response.status_code in (401, 403):
        prefix = "FortiAnalyzer credentials rejected or trusted host/profile denied the request"
    elif response.status_code == 404:
        prefix = "FortiAnalyzer JSON-RPC endpoint not found; check host URL and firmware version"
    else:
        prefix = f"FortiAnalyzer API request failed with HTTP {response.status_code}"
    detail = _response_error_excerpt(response)
    return f"{prefix}: {detail}" if detail else prefix


def _response_error_excerpt(response: httpx.Response, *, max_length: int = 240) -> str:
    text = response.text.strip()
    if not text:
        return ""
    try:
        payload = response.json()
    except ValueError:
        excerpt = text
    else:
        excerpt = _json_excerpt(payload)
    return excerpt[:max_length]


def _json_excerpt(payload: Any, *, max_length: int = 240) -> str:
    try:
        return jsonlib.dumps(payload, sort_keys=True, separators=(",", ":"))[:max_length]
    except TypeError:
        return str(payload)[:max_length]
```

```python
# connector/__init__.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from .fortianalyzer_client import FortiAnalyzerApiClient, FortiAnalyzerApiError


def _normalize_device(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "vendor": "Fortinet",
        "product": "FortiAnalyzer",
        "hostname": str(payload.get("hostname") or payload.get("hostName") or "FortiAnalyzer"),
        "model": str(payload.get("platform_str") or payload.get("model") or "FortiAnalyzer"),
        "version": str(payload.get("version") or payload.get("firmware") or ""),
        "serial": str(payload.get("serial") or payload.get("serialNumber") or ""),
    }


class FortiAnalyzerConnector:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        client: FortiAnalyzerApiClient | None = None,
    ) -> None:
        self.config = config
        self._client = client

    def _ensure_client(self) -> FortiAnalyzerApiClient:
        if self._client is None:
            self._client = FortiAnalyzerApiClient(
                host=str(self.config.get("host") or "").rstrip("/"),
                api_key=str(self.config.get("apiKey") or ""),
                verify_tls=bool(self.config.get("verifyTls", False)),
            )
        return self._client

    def health_check(self) -> dict[str, Any]:
        host = str(self.config.get("host") or "").rstrip("/")
        if not host:
            return {
                "ok": False,
                "status": "missing_host",
                "device": {},
                "message": "FortiAnalyzer host is required",
            }
        try:
            device = _normalize_device(self._ensure_client().get_system_status())
        except (FortiAnalyzerApiError, ValueError) as exc:
            return {
                "ok": False,
                "status": "disconnected",
                "device": {},
                "message": str(exc),
            }
        return {
            "ok": True,
            "status": "connected",
            "device": device,
            "message": "FortiAnalyzer JSON-RPC API reachable",
        }

    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]:
        _ = req
        return {"status": "ready", "data": {}, "meta": {"source": "fortianalyzer"}}

    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]:
        _ = since
        return []

    def close(self) -> None:
        self._client = None


def get_connector(config: dict[str, Any]) -> FortiAnalyzerConnector:
    return FortiAnalyzerConnector(config)
```

- [ ] **Step 3: Add manifest, README, and catalog entry**

Create `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/addon.json`:

```json
{
  "id": "fortianalyzer-core",
  "version": "0.1.0-beta.1",
  "name": "FortiAnalyzer Core Beta",
  "vendor": "Fortinet",
  "category": "siem",
  "description": "SIEM analytics beta for FortiAnalyzer: marketplace listing, JSON-RPC health probe scaffold, preview widgets, and draft-only analyst playbook actions. Appliance validation is pending.",
  "icon": "fortinet",
  "minDashboardVersion": "0.1.0",
  "provider": {
    "type": "fortianalyzer",
    "auth": {
      "kind": "apiKey",
      "fields": [
        {
          "id": "host",
          "label": "FortiAnalyzer URL",
          "type": "url",
          "required": true,
          "placeholder": "https://fortianalyzer.example.local"
        },
        {
          "id": "apiKey",
          "label": "API Key",
          "type": "secret",
          "required": true
        },
        {
          "id": "verifyTls",
          "label": "Verify TLS",
          "type": "boolean",
          "default": false
        }
      ]
    }
  },
  "compatibility": {
    "minProviderVersion": "7.6.0",
    "testedVersions": [],
    "notes": "Beta/unvalidated marketplace preview. The team does not currently have a FortiAnalyzer appliance for validation. Requires a FortiAnalyzer REST API Admin with JSON API read access and trusted hosts that allow the Penguard API source IP. Health check uses POST /jsonrpc with url /sys/status. Widgets and playbook actions are preview/draft-only and are not appliance-validated."
  },
  "capabilities": {
    "logSource": true,
    "playbookTarget": true,
    "managed": true
  },
  "routes": [
    {
      "id": "jsonrpc-system-status",
      "method": "POST",
      "path": "/jsonrpc",
      "summary": "Read-only JSON-RPC get request with url /sys/status."
    }
  ],
  "widgets": [
    "fortianalyzer-health-preview",
    "fortianalyzer-adom-log-posture",
    "fortianalyzer-top-event-types",
    "fortianalyzer-ingestion-readiness"
  ],
  "siemEventTypes": [],
  "entrypoint": "connector",
  "requirements": [
    "httpx>=0.27,<1.0"
  ]
}
```

Create `/home/guest/penguard-addons/fortianalyzer-core/0.1.0-beta.1/README.md`:

```markdown
# FortiAnalyzer Core 0.1.0 Beta

Beta FortiAnalyzer marketplace listing for Penguard. This package exists
so FortiAnalyzer appears in the marketplace while appliance validation is still
pending.

## Authentication

Use a FortiAnalyzer REST API Admin API key with JSON API read access. Configure
trusted hosts so FortiAnalyzer accepts requests from the Penguard API
source IP.

## Current scope

- Health probe: `POST /jsonrpc` with `method=get` and `url=/sys/status`.
- Marketplace listing and installable package metadata.
- Preview widgets for health, ADOM/log posture, event taxonomy and ingestion
  readiness. All widget payloads are marked `applianceValidated=false`.
- Event ingestion: empty list until log/ADOM pagination is validated in a lab.
- Draft-only playbook action for analyst signal review. It is always `dryRun`
  and never changes FortiAnalyzer state.

No configuration writes, live log ingestion, live widgets, or live playbook
actions are included in this beta package.
```

Add this object to root `/home/guest/penguard-addons/catalog.json` after
the `fortiweb-core` entry and before Penguin entries:

```json
{
  "id": "fortianalyzer-core",
  "name": "FortiAnalyzer Core Beta",
  "vendor": "Fortinet",
  "category": "siem",
  "icon": "fortinet",
  "description": "SIEM analytics beta for FortiAnalyzer: marketplace listing, JSON-RPC health probe scaffold, preview widgets, and draft-only analyst playbook actions. Appliance validation is pending.",
  "latestVersion": "0.1.0-beta.1",
  "versions": ["0.1.0-beta.1"],
  "tagTemplate": "fortianalyzer-core-v{version}"
}
```

- [ ] **Step 4: Run package tests**

Run:

```bash
cd /home/guest/penguard-addons
python -m pytest fortianalyzer-core/0.1.0-beta.1/tests/test_connector.py -q
```

Expected: all tests pass.

### Task 3: Validate And Publish

**Files:**
- Modify: Git metadata in `/home/guest/penguard-addons`

- [ ] **Step 1: Run registry verification**

Run:

```bash
cd /home/guest/penguard-addons
python -m pytest fortianalyzer-core/0.1.0-beta.1/tests/test_connector.py -q
git diff --check
git status -sb
```

Expected: pytest exits 0, diff check exits 0, status only contains the
FortiAnalyzer package and catalog changes.

- [ ] **Step 2: Commit on a feature branch**

Run:

```bash
cd /home/guest/penguard-addons
git switch -c codex/fortianalyzer-core-addon
git add catalog.json fortianalyzer-core/0.1.0-beta.1
git commit -m "feat(fortianalyzer-core): add read-only connector"
```

- [ ] **Step 3: Publish to GitHub**

Use the GitHub app or git push to publish branch
`codex/fortianalyzer-core-addon` to `ping-wins/penguard-addons` and open
a draft PR against `main`. Do not create the release tag
`fortianalyzer-core-v0.1.0-beta.1` until the PR is merged or the user explicitly asks
for direct release tagging.
