# XDR Windows Daemon And CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Windows lab agent's TUI-first runtime with a manageable daemon/service model, local CLI control and a typed XDR action queue.

**Architecture:** `agent_private` gets a daemon layer that reuses the existing telemetry runner, exposes a loopback control API for local CLI commands and wraps the daemon as a Windows Service on Windows. `xdr_rico` stores typed endpoint actions, while `apps/api` forwards dashboard-created actions and agent claim/result calls through the BFF.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, httpx, psutil, pywin32 on Windows only, Pytest, Ruff, Vue follow-up later.

---

## File Structure

- Create `apps/agent_private/agent_private/control.py`: loopback JSON control server/client used by the daemon and local CLI.
- Create `apps/agent_private/agent_private/daemon.py`: long-running daemon orchestration around telemetry posting and local control.
- Create `apps/agent_private/agent_private/windows_service.py`: Windows Service wrapper with lazy `pywin32` imports.
- Modify `apps/agent_private/agent_private/runner.py`: expose one-shot telemetry payload collection/posting helpers reusable by daemon and control API.
- Modify `apps/agent_private/agent_private/cli.py`: add `daemon`, `status`, `collect-now`, `config` and `service` subcommands.
- Modify `apps/agent_private/README.md`: document daemon/service-first Windows lab flow.
- Modify `apps/agent_private/pyproject.toml`: add Windows-only `pywin32` dependency.
- Create `apps/agent_private/tests/test_control.py`: local control server/client behavior.
- Create `apps/agent_private/tests/test_daemon.py`: daemon status and collect-now behavior.
- Create `apps/agent_private/tests/test_windows_service.py`: non-Windows guard and command delegation tests.
- Modify `apps/agent_private/tests/test_cli.py`: CLI routing for daemon/service/status/config/collect-now.
- Modify `apps/xdr_rico/app/store.py`: add endpoint action persistence table and store methods.
- Modify `apps/xdr_rico/app/main.py`: add action models and endpoints.
- Modify `apps/xdr_rico/tests/test_core.py`: action queue lifecycle tests.
- Modify `apps/api/app/routers/soc.py`: add BFF forwarding/audit endpoints for XDR actions.
- Modify `apps/api/tests/test_soc_gateway.py`: BFF action forwarding and bearer pass-through tests.
- Modify `docs/product/feature-map.md`: note XDR daemon/action-queue status after implementation.

## Task 1: Agent Control API

**Files:**
- Create: `apps/agent_private/agent_private/control.py`
- Test: `apps/agent_private/tests/test_control.py`

- [ ] **Step 1: Write failing tests**

```python
from agent_private.control import (
    AgentControlClient,
    AgentControlState,
    AgentControlServer,
)


def test_control_status_returns_redacted_runtime_state():
    state = AgentControlState(
        endpoint_id="end_win_01",
        started_at=100.0,
        sent_count=2,
        failed_count=1,
        last_event="heartbeat",
    )
    server = AgentControlServer(state=state, collect_now=lambda kind: {"posted": []})
    with server.running(port=0) as address:
        payload = AgentControlClient(base_url=f"http://{address.host}:{address.port}").status()

    assert payload["endpointId"] == "end_win_01"
    assert payload["sentCount"] == 2
    assert payload["failedCount"] == 1
    assert "token" not in repr(payload).lower()
```

- [ ] **Step 2: Verify red**

Run: `cd apps/agent_private && uv run pytest tests/test_control.py -q`

Expected: import failure for `agent_private.control`.

- [ ] **Step 3: Implement minimal control server/client**

Create a standard-library HTTP server bound to `127.0.0.1`. Implement:

- `AgentControlState.to_status_payload()`
- `AgentControlServer.running(port=0)`
- `AgentControlClient.status()`
- `AgentControlClient.collect_now(kind)`

- [ ] **Step 4: Verify green**

Run: `cd apps/agent_private && uv run pytest tests/test_control.py -q`

Expected: all control tests pass.

## Task 2: Daemon Runtime

**Files:**
- Create: `apps/agent_private/agent_private/daemon.py`
- Modify: `apps/agent_private/agent_private/runner.py`
- Test: `apps/agent_private/tests/test_daemon.py`

- [ ] **Step 1: Write failing daemon tests**

```python
from agent_private.daemon import AgentDaemon
from agent_private.runner import AgentRunConfig


def test_daemon_collect_now_posts_requested_payloads():
    posted = []
    daemon = AgentDaemon(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_01",
            enrollment_token="secret-token",
        ),
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        identity_provider=lambda: {"service": "agent_private", "hostname": "WIN", "username": "lab", "os": "Windows"},
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [{"pid": 1, "name": "lsass.exe"}],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
    )

    result = daemon.collect_now("processes")

    assert result["posted"] == ["process.snapshot"]
    assert posted[0]["eventType"] == "process.snapshot"
    assert daemon.status()["sentCount"] == 1
```

- [ ] **Step 2: Verify red**

Run: `cd apps/agent_private && uv run pytest tests/test_daemon.py -q`

Expected: import failure for `agent_private.daemon`.

- [ ] **Step 3: Implement daemon shell**

Implement `AgentDaemon.status()`, `AgentDaemon.collect_now(kind)` and
`AgentDaemon.run_foreground(control_port=8765)` using the new control server.
The daemon should not print or return enrollment tokens.

- [ ] **Step 4: Verify green**

Run: `cd apps/agent_private && uv run pytest tests/test_daemon.py tests/test_runner.py -q`

Expected: daemon and existing runner tests pass.

## Task 3: CLI And Windows Service Wrapper

**Files:**
- Create: `apps/agent_private/agent_private/windows_service.py`
- Modify: `apps/agent_private/agent_private/cli.py`
- Modify: `apps/agent_private/pyproject.toml`
- Test: `apps/agent_private/tests/test_cli.py`
- Test: `apps/agent_private/tests/test_windows_service.py`

- [ ] **Step 1: Write failing CLI/service tests**

Add tests that prove:

- `agent-private status` calls `AgentControlClient.status()`.
- `agent-private collect-now processes` calls `AgentControlClient.collect_now("processes")`.
- `agent-private service status` delegates to `windows_service.service_status()`.
- On non-Windows, service commands raise a clear `RuntimeError`.

- [ ] **Step 2: Verify red**

Run: `cd apps/agent_private && uv run pytest tests/test_cli.py tests/test_windows_service.py -q`

Expected: missing command or import failures.

- [ ] **Step 3: Implement CLI/service**

Add CLI subcommands:

```txt
agent-private daemon
agent-private status
agent-private collect-now heartbeat|processes|connections|windows-security|all
agent-private config show
agent-private config set --api-url URL --endpoint-id ID --enrollment-token TOKEN
agent-private service install|start|stop|status|uninstall
```

Add Windows-only service support through lazy `pywin32` imports and keep Linux
imports safe.

- [ ] **Step 4: Verify green**

Run: `cd apps/agent_private && uv run pytest -q && uv run ruff check agent_private tests`

Expected: agent package tests and lint pass.

## Task 4: XDR Action Queue

**Files:**
- Modify: `apps/xdr_rico/app/store.py`
- Modify: `apps/xdr_rico/app/main.py`
- Test: `apps/xdr_rico/tests/test_core.py`

- [ ] **Step 1: Write failing action lifecycle tests**

Add tests for:

- Creating a `collect_now` action for an existing endpoint.
- Claiming the next queued action with the endpoint enrollment bearer token.
- Posting a completed result.
- Rejecting a result for a different endpoint/token binding.

- [ ] **Step 2: Verify red**

Run: `cd apps/xdr_rico && uv run pytest tests/test_core.py -q`

Expected: missing action endpoints.

- [ ] **Step 3: Implement action persistence and endpoints**

Add `xdr_rico_endpoint_actions` table and store methods. Add FastAPI endpoints:

```txt
POST /endpoints/{endpoint_id}/actions
GET  /endpoints/{endpoint_id}/actions
POST /endpoints/{endpoint_id}/actions/claim
POST /endpoints/{endpoint_id}/actions/{action_id}/result
```

- [ ] **Step 4: Verify green**

Run: `cd apps/xdr_rico && uv run pytest -q && uv run ruff check app tests`

Expected: XDR tests and lint pass.

## Task 5: BFF Action Gateway

**Files:**
- Modify: `apps/api/app/routers/soc.py`
- Test: `apps/api/tests/test_soc_gateway.py`

- [ ] **Step 1: Write failing BFF tests**

Add tests that prove:

- Browser action creation uses CSRF and audits `xdr.endpoint_action.created`.
- Agent action claim forwards `Authorization: Bearer ...` without CSRF.
- Agent result posts audit-safe metadata and forwards bearer auth.

- [ ] **Step 2: Verify red**

Run: `cd apps/api && uv run pytest tests/test_soc_gateway.py -q`

Expected: missing `/api/weapons/endpoints/{id}/actions...` routes.

- [ ] **Step 3: Implement gateway routes**

Add BFF routes under `/api/weapons/endpoints/{endpoint_id}/actions`. Do not log
tokens. Browser-created actions require auth/CSRF. Agent claim/result require
bearer auth only.

- [ ] **Step 4: Verify green**

Run: `cd apps/api && uv run pytest tests/test_soc_gateway.py -q`

Expected: gateway tests pass.

## Task 6: Agent Remote Action Polling

**Files:**
- Modify: `apps/agent_private/agent_private/daemon.py`
- Modify: `apps/agent_private/agent_private/runner.py`
- Test: `apps/agent_private/tests/test_daemon.py`

- [ ] **Step 1: Write failing action polling test**

Add a test proving the daemon claims a `collect_now` action, posts the requested
telemetry, and posts a completed action result.

- [ ] **Step 2: Verify red**

Run: `cd apps/agent_private && uv run pytest tests/test_daemon.py -q`

Expected: missing action polling behavior.

- [ ] **Step 3: Implement polling**

Add an optional polling interval to `AgentRunConfig` or `AgentDaemon`. Use the
BFF endpoints:

```txt
POST /api/weapons/endpoints/{endpointId}/actions/claim
POST /api/weapons/endpoints/{endpointId}/actions/{actionId}/result
```

Only implement `collect_now` and `run_diagnostic` handlers. Unknown actions are
reported as failed.

- [ ] **Step 4: Verify green**

Run: `cd apps/agent_private && uv run pytest -q && uv run ruff check agent_private tests`

Expected: agent tests and lint pass.

## Task 7: Docs And Product Status

**Files:**
- Modify: `apps/agent_private/README.md`
- Modify: `docs/product/feature-map.md`

- [ ] **Step 1: Update docs**

Document:

- Windows Service-first lab flow.
- CLI commands.
- TUI as troubleshooting-only.
- Remote action safety boundary.

- [ ] **Step 2: Verify docs and full checks**

Run:

```bash
git diff --check
cd apps/agent_private && uv run pytest -q && uv run ruff check agent_private tests
cd apps/xdr_rico && uv run pytest -q && uv run ruff check app tests
cd apps/api && uv run pytest tests/test_soc_gateway.py -q
```

Expected: all commands pass.

## Self-Review

- Spec coverage: daemon/service model, local CLI, loopback control API, XDR
  action queue, BFF gateway and remote collect-now are all mapped to tasks.
- Scope check: dashboard UI changes are intentionally deferred beyond backend
  action availability because the user asked first for daemon/CLI behavior.
- Placeholder scan: no task depends on an undefined endpoint or command.
- Type consistency: action statuses and action kinds match the design spec.
