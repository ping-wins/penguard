# Penguin Tools Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first clean implementation slice for the Penguin SOC-lite tools: shared contracts/catalog, service scaffolds, Docker Compose wiring and baseline tests.

**Architecture:** Keep FortiDashboard as the browser-facing BFF and add independent headless apps for `siem_kowalski`, `soar_skipper`, `xdr_rico` and `agent_private`. This phase intentionally avoids business logic beyond health/metadata so later phases can implement SIEM, SOAR and XDR behavior behind stable boundaries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Pytest, Ruff, Docker Compose, Postgres, Redis, JSON fixtures in `packages/contracts` and metadata in `packages/soc-catalog`.

---

## File Structure

- Create `packages/soc-catalog/package.json`: workspace package metadata.
- Create `packages/soc-catalog/README.md`: catalog purpose and ownership.
- Create `packages/soc-catalog/event-types.json`: initial SOC event taxonomy.
- Create `packages/soc-catalog/playbook-node-types.json`: allowed Skipper workflow nodes.
- Create `packages/soc-catalog/widgets.json`: SOC widget metadata consumed by the cockpit.
- Create `packages/contracts/fixtures/security_event.json`: example Kowalski event.
- Create `packages/contracts/fixtures/incident.json`: example Kowalski incident.
- Create `packages/contracts/fixtures/endpoint.json`: example Rico endpoint.
- Create `packages/contracts/fixtures/endpoint_event.json`: example Rico endpoint event.
- Create `packages/contracts/fixtures/playbook.json`: example Skipper playbook.
- Create `packages/contracts/fixtures/playbook_run.json`: example Skipper playbook run.
- Create `apps/siem_kowalski/*`: FastAPI scaffold and tests.
- Create `apps/soar_skipper/*`: FastAPI scaffold and tests.
- Create `apps/xdr_rico/*`: FastAPI scaffold and tests.
- Create `apps/agent_private/*`: Python CLI scaffold and tests.
- Modify `docker-compose.yml`: add Redis and the three headless service containers.
- Modify `.env.example`: add service URL and Redis defaults.
- Modify `AGENTS.md`: mark Phase 1 scaffold items as complete only after verification passes.

## Task 1: Shared SOC Catalog and Fixtures

**Files:**
- Create: `packages/soc-catalog/package.json`
- Create: `packages/soc-catalog/README.md`
- Create: `packages/soc-catalog/event-types.json`
- Create: `packages/soc-catalog/playbook-node-types.json`
- Create: `packages/soc-catalog/widgets.json`
- Create: `packages/contracts/fixtures/security_event.json`
- Create: `packages/contracts/fixtures/incident.json`
- Create: `packages/contracts/fixtures/endpoint.json`
- Create: `packages/contracts/fixtures/endpoint_event.json`
- Create: `packages/contracts/fixtures/playbook.json`
- Create: `packages/contracts/fixtures/playbook_run.json`

- [ ] **Step 1: Add package metadata**

Create `packages/soc-catalog/package.json`:

```json
{
  "name": "@fortidashboard/soc-catalog",
  "version": "0.1.0",
  "private": true
}
```

- [ ] **Step 2: Add catalog README**

Create `packages/soc-catalog/README.md`:

```markdown
# SOC Catalog

Shared SOC-lite metadata for FortiDashboard and the Penguin tools.

- `event-types.json` defines normalized event classes used by `siem_kowalski`.
- `playbook-node-types.json` defines allowed workflow nodes used by `soar_skipper`.
- `widgets.json` defines SOC widgets that can be surfaced in the FortiDashboard cockpit.

This package contains static metadata only. Runtime state belongs in the owning app tables.
```

- [ ] **Step 3: Add event taxonomy**

Create `packages/soc-catalog/event-types.json`:

```json
{
  "items": [
    {
      "id": "network.deny",
      "label": "Denied Network Traffic",
      "defaultSeverity": "medium",
      "entityFields": ["sourceIp", "destinationIp", "integrationId"]
    },
    {
      "id": "network.scan",
      "label": "Possible Network Scan",
      "defaultSeverity": "high",
      "entityFields": ["sourceIp", "destinationIp"]
    },
    {
      "id": "auth.failed_login",
      "label": "Failed Login",
      "defaultSeverity": "medium",
      "entityFields": ["username", "sourceIp"]
    },
    {
      "id": "endpoint.process_snapshot",
      "label": "Endpoint Process Snapshot",
      "defaultSeverity": "low",
      "entityFields": ["endpointId", "hostname", "username"]
    },
    {
      "id": "endpoint.suspicious_connection",
      "label": "Suspicious Endpoint Connection",
      "defaultSeverity": "high",
      "entityFields": ["endpointId", "hostname", "destinationIp"]
    }
  ]
}
```

- [ ] **Step 4: Add playbook node catalog**

Create `packages/soc-catalog/playbook-node-types.json`:

```json
{
  "items": [
    { "id": "trigger.incident_created", "label": "Incident Created", "sensitive": false },
    { "id": "condition.severity", "label": "Severity Condition", "sensitive": false },
    { "id": "enrich.ip", "label": "Enrich IP", "sensitive": false },
    { "id": "case.note", "label": "Create Case Note", "sensitive": false },
    { "id": "approval.required", "label": "Require Approval", "sensitive": false },
    { "id": "notify.webhook", "label": "Notify Webhook", "sensitive": false },
    { "id": "fortigate.recommend_block", "label": "Recommend FortiGate Block", "sensitive": true }
  ]
}
```

- [ ] **Step 5: Add SOC widget catalog**

Create `packages/soc-catalog/widgets.json`:

```json
{
  "items": [
    {
      "id": "soc-open-incidents-by-severity",
      "title": "Open Incidents by Severity",
      "source": "siem_kowalski",
      "template": "bar_chart",
      "defaultSize": { "w": 4, "h": 3 }
    },
    {
      "id": "soc-recent-incidents",
      "title": "Recent Incidents",
      "source": "siem_kowalski",
      "template": "event_feed",
      "defaultSize": { "w": 5, "h": 4 }
    },
    {
      "id": "soc-endpoint-health",
      "title": "Endpoint Health",
      "source": "xdr_rico",
      "template": "status_list",
      "defaultSize": { "w": 4, "h": 3 }
    },
    {
      "id": "soc-active-playbook-runs",
      "title": "Active Playbook Runs",
      "source": "soar_skipper",
      "template": "table",
      "defaultSize": { "w": 5, "h": 3 }
    }
  ]
}
```

- [ ] **Step 6: Add contract fixtures**

Create the six fixture JSON files listed above using the payload examples already documented in `AGENTS.md`. Each fixture must use stable IDs (`evt_01`, `inc_01`, `end_01`, `pb_01`, `pbr_01`) and must not include secrets.

- [ ] **Step 7: Verify JSON parses**

Run:

```bash
python -m json.tool packages/soc-catalog/event-types.json >/tmp/event-types.json
python -m json.tool packages/soc-catalog/playbook-node-types.json >/tmp/playbook-node-types.json
python -m json.tool packages/soc-catalog/widgets.json >/tmp/widgets.json
python -m json.tool packages/contracts/fixtures/security_event.json >/tmp/security_event.json
python -m json.tool packages/contracts/fixtures/incident.json >/tmp/incident.json
python -m json.tool packages/contracts/fixtures/endpoint.json >/tmp/endpoint.json
python -m json.tool packages/contracts/fixtures/endpoint_event.json >/tmp/endpoint_event.json
python -m json.tool packages/contracts/fixtures/playbook.json >/tmp/playbook.json
python -m json.tool packages/contracts/fixtures/playbook_run.json >/tmp/playbook_run.json
```

Expected: all commands exit `0`.

## Task 2: Scaffold Penguin FastAPI Services

**Files:**
- Create: `apps/siem_kowalski/pyproject.toml`
- Create: `apps/siem_kowalski/Dockerfile`
- Create: `apps/siem_kowalski/app/__init__.py`
- Create: `apps/siem_kowalski/app/main.py`
- Create: `apps/siem_kowalski/tests/test_health.py`
- Repeat equivalent files for `apps/soar_skipper` and `apps/xdr_rico`.

- [ ] **Step 1: Write the failing health tests**

Create `tests/test_health.py` in each service with service-specific expected names:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_service_identity():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "siem_kowalski"}
```

For `soar_skipper`, replace expected service with `soar_skipper`. For `xdr_rico`, replace it with `xdr_rico`.

- [ ] **Step 2: Add minimal FastAPI app**

Create `app/main.py` in each service:

```python
from fastapi import FastAPI

SERVICE_NAME = "siem_kowalski"

app = FastAPI(title="siem_kowalski", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
```

Use the matching service name in each app.

- [ ] **Step 3: Add service pyproject**

Create each service `pyproject.toml`:

```toml
[project]
name = "siem-kowalski"
version = "0.1.0"
description = "SIEM-lite service for FortiDashboard"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "pydantic>=2.8.0",
    "uvicorn[standard]>=0.30.0"
]

[dependency-groups]
dev = [
    "pytest>=8.2.0",
    "ruff>=0.5.0"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Use `soar-skipper` and `xdr-rico` names/descriptions for the other services.

- [ ] **Step 4: Add Dockerfiles**

Create each service `Dockerfile`:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app/apps/siem_kowalski

COPY apps/siem_kowalski/pyproject.toml ./
RUN uv sync --no-dev

COPY apps/siem_kowalski/app ./app

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Use the matching path for each service.

- [ ] **Step 5: Run service tests**

Run:

```bash
cd apps/siem_kowalski && uv run pytest
cd apps/soar_skipper && uv run pytest
cd apps/xdr_rico && uv run pytest
```

Expected: all health tests pass.

## Task 3: Scaffold agent_private CLI

**Files:**
- Create: `apps/agent_private/pyproject.toml`
- Create: `apps/agent_private/agent_private/__init__.py`
- Create: `apps/agent_private/agent_private/cli.py`
- Create: `apps/agent_private/tests/test_cli.py`

- [ ] **Step 1: Write CLI test**

Create `apps/agent_private/tests/test_cli.py`:

```python
from agent_private.cli import build_identity_payload


def test_build_identity_payload_has_required_fields():
    payload = build_identity_payload(hostname="win-lab-01", username="SOC-LAB\\felipe")

    assert payload["hostname"] == "win-lab-01"
    assert payload["username"] == "SOC-LAB\\felipe"
    assert payload["service"] == "agent_private"
```

- [ ] **Step 2: Add CLI implementation**

Create `apps/agent_private/agent_private/cli.py`:

```python
import getpass
import platform
import socket


def build_identity_payload(hostname: str | None = None, username: str | None = None) -> dict[str, str]:
    return {
        "service": "agent_private",
        "hostname": hostname or socket.gethostname(),
        "username": username or getpass.getuser(),
        "os": platform.system(),
    }


def main() -> None:
    print(build_identity_payload())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add pyproject**

Create `apps/agent_private/pyproject.toml`:

```toml
[project]
name = "agent-private"
version = "0.1.0"
description = "Endpoint sensor for FortiDashboard xdr_rico"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27.0",
    "psutil>=6.0.0",
    "pydantic>=2.8.0",
    "tenacity>=9.0.0",
    "watchdog>=5.0.0"
]

[project.scripts]
agent-private = "agent_private.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.2.0",
    "ruff>=0.5.0"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
cd apps/agent_private && uv run pytest
```

Expected: test passes.

## Task 4: Docker Compose Wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Add Redis**

Add service:

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "${FORTIDASHBOARD_REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Add Penguin services**

Add services:

```yaml
  siem-kowalski:
    build:
      context: .
      dockerfile: apps/siem_kowalski/Dockerfile
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  soar-skipper:
    build:
      context: .
      dockerfile: apps/soar_skipper/Dockerfile
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  xdr-rico:
    build:
      context: .
      dockerfile: apps/xdr_rico/Dockerfile
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
```

- [ ] **Step 3: Add env defaults**

Add to `.env.example`:

```dotenv
FORTIDASHBOARD_REDIS_PORT=6379
FORTIDASHBOARD_SIEM_KOWALSKI_URL=http://siem-kowalski:8000
FORTIDASHBOARD_SOAR_SKIPPER_URL=http://soar-skipper:8000
FORTIDASHBOARD_XDR_RICO_URL=http://xdr-rico:8000
```

- [ ] **Step 4: Validate compose config**

Run:

```bash
docker compose config >/tmp/fortidashboard-compose.yml
```

Expected: command exits `0`.

## Task 5: Documentation and Verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update AGENTS backlog**

Mark only these checked items:

```markdown
- [x] Create `packages/soc-catalog` with severities, event classes, entity fields, playbook node types and widget metadata.
- [x] Add schemas/fixtures for `SecurityEvent`, `Incident`, `Endpoint`, `EndpointEvent`, `Playbook`, `PlaybookRun` and `PlaybookStepRun`.
- [x] Add Redis to Docker Compose for workers.
- [x] Add `apps/siem_kowalski` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/soar_skipper` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/xdr_rico` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/agent_private` scaffold as Python CLI package.
```

- [ ] **Step 2: Run final verification**

Run:

```bash
python -m json.tool packages/soc-catalog/event-types.json >/tmp/event-types.json
cd apps/siem_kowalski && uv run pytest
cd apps/soar_skipper && uv run pytest
cd apps/xdr_rico && uv run pytest
cd apps/agent_private && uv run pytest
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 3: Commit**

Run:

```bash
git add AGENTS.md .env.example docker-compose.yml docs/superpowers/plans/2026-05-08-penguin-tools-foundation.md packages/soc-catalog packages/contracts/fixtures apps/siem_kowalski apps/soar_skipper apps/xdr_rico apps/agent_private
git commit -m "feat: scaffold penguin soc tools"
```

Expected: commit succeeds after verification.

## Self-Review

- Spec coverage: this plan covers Phase 1 foundation only. It does not implement detection logic, playbook execution, endpoint enrollment, AI tools or frontend SOC UX.
- Placeholder scan: no step relies on unspecified paths or undefined service names.
- Type consistency: service names are consistently `siem_kowalski`, `soar_skipper`, `xdr_rico` and `agent_private`; Docker service names use hyphenated equivalents.
