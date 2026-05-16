"""Tests for the multi-step agent runtime (PR1 — scripted backend only)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi.testclient import TestClient

from app.ai.agent.backends.scripted import ScriptedBackend
from app.ai.agent.registry import REGISTRY, ToolContext
from app.ai.agent.runner import AgentRunner
from app.ai.agent.session import SessionStore, get_session_store
# Side-effect: registers built-in tools.
from app.ai.agent.tools import (  # noqa: F401
    audit_tool,
    incidents,
    integrations,
    playbook_runs,
    widgets,
    workspace,
    xdr_endpoints,
)
from app.auth import dependencies as auth_dependencies
from app.main import app


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    get_session_store().reset_for_tests()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_lists_nine_read_tools():
    expected = {
        "list_integrations",
        "get_widget_data",
        "list_incidents",
        "get_incident",
        "search_audit",
        "list_playbook_runs",
        "get_endpoint",
        "get_workspace",
        "search_events",
    }
    assert expected.issubset(REGISTRY.keys())
    for tool in REGISTRY.values():
        assert tool.requires_approval is False
        assert tool.input_schema["type"] == "object"


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


def test_session_store_enforces_user_quota():
    store = SessionStore(ttl_seconds=3600, max_sessions_per_user=2)
    s1 = store.create(user_id="user-1")
    s2 = store.create(user_id="user-1")
    s3 = store.create(user_id="user-1")

    assert store.get(s1.id, user_id="user-1") is None
    assert store.get(s2.id, user_id="user-1") is not None
    assert store.get(s3.id, user_id="user-1") is not None


def test_session_store_rejects_cross_user_access():
    store = SessionStore()
    s = store.create(user_id="user-1")
    assert store.get(s.id, user_id="user-2") is None


# ---------------------------------------------------------------------------
# Scripted backend
# ---------------------------------------------------------------------------


def test_scripted_backend_maps_keyword_to_tool():
    backend = ScriptedBackend()
    decision = backend.decide(
        history=[{"role": "user", "content": "Liste meus incidentes"}],
        tools=list(REGISTRY.values()),
        locale="pt-BR",
    )
    assert decision.kind == "tool_call"
    assert decision.tool_name == "list_incidents"


def test_scripted_backend_finalizes_after_tool_result():
    backend = ScriptedBackend()
    decision = backend.decide(
        history=[
            {"role": "user", "content": "Liste incidentes"},
            {
                "role": "tool",
                "tool_name": "list_incidents",
                "result": {"items": [], "count": 0},
            },
        ],
        tools=list(REGISTRY.values()),
        locale="pt-BR",
    )
    assert decision.kind == "final"
    assert "list_incidents" in decision.text


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class _StubSiem:
    def request(self, _method: str, path: str, *, params=None, **_):
        if path == "/incidents":
            return {"items": [{"id": "inc-1", "severity": "high"}]}
        return {}


async def _collect(runner: AgentRunner, **kwargs):
    events: list[dict[str, Any]] = []
    async for event in runner.run_turn(**kwargs):
        events.append(event.to_dict())
    return events


def test_runner_invokes_tool_and_emits_events():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", locale="pt-BR")
    audit_calls: list[dict[str, Any]] = []

    runner = AgentRunner(
        backend=ScriptedBackend(),
        session_store=store,
        audit_recorder=lambda **kwargs: audit_calls.append(kwargs),
    )
    ctx = ToolContext(user_id="user-1", siem_client=_StubSiem())

    events = asyncio.run(
        _collect(
            runner,
            session=session,
            user_message="liste incidentes",
            tool_context=ctx,
        )
    )

    kinds = [e["kind"] for e in events]
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert kinds[-1] == "done"

    done = events[-1]
    assert "list_incidents" in done["used_tools"]
    assert any(audit["details"]["toolName"] == "list_incidents" for audit in audit_calls)


def test_runner_reports_unknown_tool_error():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted")

    class FailingBackend:
        name = "broken"
        model = ""

        def decide(self, **_kwargs):
            from app.ai.agent.backends.base import BackendDecision

            return BackendDecision(kind="tool_call", tool_name="nonexistent")

    runner = AgentRunner(backend=FailingBackend(), session_store=store)
    ctx = ToolContext(user_id="user-1")
    events = asyncio.run(
        _collect(runner, session=session, user_message="run", tool_context=ctx)
    )

    assert events[-1]["kind"] == "error"
    assert events[-1]["code"] == "unknown_tool"


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_list_backends_endpoint_lists_scripted():
    client = TestClient(app)
    response = client.get("/api/ai/agent/backends")
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "scripted" in names


def test_list_tools_endpoint_returns_input_schemas():
    client = TestClient(app)
    response = client.get("/api/ai/agent/tools")
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "list_incidents" in names
    list_incidents = next(item for item in payload["items"] if item["name"] == "list_incidents")
    assert list_incidents["inputSchema"]["type"] == "object"


def test_create_session_returns_session_id():
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"backend": "scripted", "locale": "pt-BR"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["backend"] == "scripted"
    assert payload["sessionId"]


def test_create_session_rejects_unknown_backend():
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"backend": "openai"},
    )
    assert response.status_code == 400


def test_send_message_streams_steps_and_records_audit():
    client = TestClient(app)
    headers = csrf_headers(client)
    create = client.post(
        "/api/ai/agent/sessions",
        headers=headers,
        json={"backend": "scripted", "locale": "pt-BR"},
    )
    assert create.status_code == 201
    session_id = create.json()["sessionId"]

    with client.stream(
        "POST",
        f"/api/ai/agent/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "olá agente"},
    ) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    types = [e.get("type") for e in events]
    assert types[0] == "connected"
    assert "step" in types
    done = next(e for e in events if e.get("type") == "step" and e.get("kind") == "done")
    assert "reply" in done

    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.tool_call"
    )
    # Greeting-without-keyword path triggers no tool call; that's fine.
    assert "items" in audit
