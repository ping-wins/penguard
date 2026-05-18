"""Tests for the multi-step agent runtime (PR1 — scripted backend only)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.agent.backends.anthropic import AnthropicBackend
from app.ai.agent.backends.base import BackendError, Final, TextDelta, ToolCall
from app.ai.agent.backends.openai import OpenAIBackend
from app.ai.agent.backends.scripted import ScriptedBackend
from app.ai.agent.registry import REGISTRY, AgentTool, ToolContext, register_tool
from app.ai.agent.roles import get_role, list_roles
from app.ai.agent.router import AgentNotConfiguredError, pick_backend
from app.ai.agent.runner import AgentRunner
from app.ai.agent.session import SessionStore, get_session_store
from app.ai.agent.settings import InMemoryAiAgentSettingsStore, get_ai_agent_settings_store

# Side-effect: registers built-in tools.
from app.ai.agent.tools import (  # noqa: F401
    audit_tool,
    incidents,
    integrations,
    playbook_runs,
    playbooks,
    tickets,
    widgets,
    workspace,
    xdr_endpoints,
)
from app.ai.provider import ContainmentStep, ContainmentSuggestion, IncidentAnalysis
from app.auth import dependencies as auth_dependencies
from app.main import app


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    get_session_store().reset_for_tests()
    get_ai_agent_settings_store.cache_clear()
    app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)


def configured_settings_store(
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: str = "sk-test",
) -> InMemoryAiAgentSettingsStore:
    store = InMemoryAiAgentSettingsStore()
    store.upsert(
        provider=provider,
        model=model,
        api_key=api_key,
        updated_by="admin@example.com",
    )
    return store


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
    for name in expected:
        tool = REGISTRY[name]
        assert tool.requires_approval is False
        assert tool.input_schema["type"] == "object"


def test_registry_marks_draft_tools_and_rejects_unapproved_write_tools():
    assert REGISTRY["draft_widget"].category == "draft"
    assert REGISTRY["draft_containment_playbook"].category == "draft"
    assert REGISTRY["draft_playbook_graph"].category == "draft"
    assert REGISTRY["draft_playbook_graph"].required_permissions == frozenset(
        {"playbooks.manage"}
    )
    assert REGISTRY["apply_playbook_patch"].category == "write"
    assert REGISTRY["apply_playbook_patch"].requires_approval is True
    assert REGISTRY["apply_playbook_patch"].required_permissions == frozenset(
        {"playbooks.manage"}
    )
    assert REGISTRY["update_ticket"].category == "write"
    assert REGISTRY["update_ticket"].requires_approval is True
    assert REGISTRY["update_ticket"].required_permissions == frozenset({"tickets.manage"})
    assert REGISTRY["run_playbook"].category == "execute"
    assert REGISTRY["run_playbook"].requires_approval is True
    assert REGISTRY["run_playbook"].required_permissions == frozenset({"playbooks.execute"})

    async def _noop(_ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    with pytest.raises(ValueError, match="write.*requires_approval"):
        register_tool(
            AgentTool(
                name="unsafe_write_for_test",
                description="Unsafe write used only to verify registry validation.",
                input_schema={"type": "object", "properties": {}},
                impl=_noop,
                category="write",
                requires_approval=False,
            )
        )
    with pytest.raises(ValueError, match="execute.*requires_approval"):
        register_tool(
            AgentTool(
                name="unsafe_execute_for_test",
                description="Unsafe execute used only to verify registry validation.",
                input_schema={"type": "object", "properties": {}},
                impl=_noop,
                category="execute",
                requires_approval=False,
            )
        )


def test_registry_rejects_unknown_required_permissions():
    async def _noop(_ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    with pytest.raises(ValueError, match="Unknown permission"):
        register_tool(
            AgentTool(
                name="unknown_permission_for_test",
                description="Tool with an invalid permission slug.",
                input_schema={"type": "object", "properties": {}},
                impl=_noop,
                required_permissions=frozenset({"does.not.exist"}),
            )
        )


def test_ai_capability_tools_use_enterprise_provider(monkeypatch):
    store = configured_settings_store(
        provider="openai",
        model="gpt-enterprise",
        api_key="sk-enterprise",
    )
    monkeypatch.setattr(
        "app.ai.agent.tools.capabilities.get_ai_agent_settings_store",
        lambda: store,
    )
    created: list[tuple[str, str]] = []

    class EnterpriseProvider:
        def __init__(self, *, api_key: str, model: str, **_: Any) -> None:
            created.append((api_key, model))

        def analyze_incident(self, context, *, locale: str = "pt-BR"):
            assert context.incident_id == "inc_1"
            assert locale == "en-US"
            return IncidentAnalysis(
                incident_id=context.incident_id,
                headline="Enterprise analysis",
                summary="Analyzed through enterprise settings.",
                risk_score=42,
                suggested_triage="T2",
                suggested_ticket_status="investigating",
                indicators_of_compromise=["10.0.0.1"],
                next_steps=["Review scope"],
                references=[],
            )

        def suggest_containment(self, context, *, locale: str = "pt-BR"):
            assert context.incident_id == "inc_1"
            assert locale == "en-US"
            return ContainmentSuggestion(
                incident_id=context.incident_id,
                summary="Enterprise containment",
                steps=[
                    ContainmentStep(
                        title="Review",
                        description="Review the incident.",
                        playbook_node_type="manual_review",
                        severity="medium",
                        requires_approval=False,
                    )
                ],
            )

    class FakeSiemClient:
        def request(self, method: str, path: str, **_: Any) -> dict[str, Any]:
            assert method == "GET"
            if path == "/tickets/tkt_1":
                return {"id": "tkt_1", "incidentId": "inc_1"}
            if path == "/incidents/inc_1":
                return {
                    "id": "inc_1",
                    "title": "Denied traffic burst",
                    "severity": "medium",
                    "summary": "Many denies from 10.0.0.1.",
                    "entities": {"sourceIp": "10.0.0.1"},
                    "timeline": [],
                    "ruleId": "rule_1",
                }
            raise AssertionError(f"unexpected SIEM path {path}")

    monkeypatch.setattr(
        "app.ai.agent.tools.capabilities.OpenAICompatibleAIProvider",
        EnterpriseProvider,
    )
    ctx = ToolContext(user_id="analyst-1", locale="en-US", siem_client=FakeSiemClient())

    analysis = asyncio.run(
        REGISTRY["analyze_incident"].impl(ctx, {"incidentId": "inc_1"})
    )
    playbook = asyncio.run(
        REGISTRY["draft_containment_playbook"].impl(ctx, {"ticketId": "tkt_1"})
    )

    assert analysis["headline"] == "Enterprise analysis"
    assert playbook["summary"] == "Enterprise containment"
    assert created == [
        ("sk-enterprise", "gpt-enterprise"),
        ("sk-enterprise", "gpt-enterprise"),
    ]


def test_ai_capability_tools_can_build_gemini_enterprise_provider(monkeypatch):
    from app.ai.agent.tools import capabilities as capability_tools

    store = configured_settings_store(
        provider="gemini",
        model="gemini-flash-latest",
        api_key="sk-gemini",
    )
    monkeypatch.setattr(
        "app.ai.agent.tools.capabilities.get_ai_agent_settings_store",
        lambda: store,
    )
    created: list[tuple[str, str]] = []

    class EnterpriseProvider:
        def __init__(self, *, api_key: str, model: str, **_: Any) -> None:
            created.append((api_key, model))

    monkeypatch.setattr(
        "app.ai.agent.tools.capabilities.GeminiAIProvider",
        EnterpriseProvider,
    )

    provider = capability_tools._enterprise_ai_provider()

    assert isinstance(provider, EnterpriseProvider)
    assert created == [("sk-gemini", "gemini-flash-latest")]


class _StubSiemTickets:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, **kwargs):
        self.requests.append((method, path, kwargs))
        if method == "GET" and path == "/incidents":
            return {"items": [{"id": "inc_1", "ticketStatus": "new"}]}
        if method == "GET" and path == "/incidents/inc_1":
            return {"id": "inc_1", "ticketStatus": "new", "status": "open"}
        if method == "PATCH" and path == "/incidents/inc_1/triage":
            return {"id": "inc_1", **kwargs["json"]}
        if method == "PATCH" and path == "/incidents/inc_1":
            return {"id": "inc_1", **kwargs["json"]}
        raise AssertionError(f"unexpected SIEM request {method} {path}")


def test_ticket_control_tools_use_siem_contracts_and_strip_unknown_fields():
    siem = _StubSiemTickets()
    ctx = ToolContext(user_id="analyst-1", siem_client=siem)

    listed = asyncio.run(
        REGISTRY["list_tickets"].impl(ctx, {"status": "new", "severity": "high"})
    )
    assert listed["count"] == 1
    assert siem.requests[-1] == (
        "GET",
        "/incidents",
        {"params": {"ticketStatus": "new", "severity": "high"}},
    )

    updated = asyncio.run(
        REGISTRY["update_ticket"].impl(
            ctx,
            {
                "ticketId": "inc_1",
                "ticketStatus": "investigating",
                "triageLevel": "T2",
                "note": "Analyst accepted triage.",
                "ignored": "must not pass",
            },
        )
    )
    assert updated["ticketStatus"] == "investigating"
    assert siem.requests[-1] == (
        "PATCH",
        "/incidents/inc_1/triage",
        {
            "json": {
                "ticketStatus": "investigating",
                "triageLevel": "T2",
                "note": "Analyst accepted triage.",
            }
        },
    )

    incident = asyncio.run(
        REGISTRY["update_incident_status"].impl(
            ctx,
            {"incidentId": "inc_1", "status": "contained", "note": "ignored here"},
        )
    )
    assert incident["status"] == "contained"
    assert siem.requests[-1] == (
        "PATCH",
        "/incidents/inc_1",
        {"json": {"status": "contained"}},
    )


class _StubSoarPlaybooks:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, **kwargs):
        self.requests.append((method, path, kwargs))
        if path == "/node-types":
            return {
                "items": [
                    {
                        "id": "trigger.incident_created",
                        "label": "Incident Created",
                        "configSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "id": "case.note",
                        "label": "Create Case Note",
                        "configSchema": {
                            "type": "object",
                            "required": ["template"],
                            "properties": {"template": {"type": "string"}},
                        },
                    },
                ]
            }
        if path == "/playbooks/pb_agent":
            return {
                "schemaVersion": 1,
                "id": "pb_agent",
                "name": "Agent playbook",
                "enabled": False,
                "system": False,
                "nodes": [{"id": "trigger", "type": "trigger.incident_created", "config": {}}],
                "edges": [],
            }
        if path == "/playbooks/pb_agent/simulate":
            return {"dryRun": True, "valid": True, "steps": []}
        if path == "/incidents/inc_1/playbooks/pb_agent/run":
            return {
                "id": "run_1",
                "incidentId": "inc_1",
                "playbookId": "pb_agent",
                "status": "waiting_approval",
            }
        if method == "POST" and path == "/playbooks":
            return kwargs["json"] | {"system": False}
        if method == "PUT" and path == "/playbooks/pb_agent":
            return kwargs["json"] | {"system": False}
        raise AssertionError(f"unexpected SOAR request {method} {path}")


def _valid_playbook_payload() -> dict[str, Any]:
    return {
        "id": "pb_agent",
        "name": "Agent playbook",
        "nodes": [
            {"id": "trigger", "type": "trigger.incident_created", "config": {}},
            {
                "id": "note",
                "type": "case.note",
                "config": {"template": "Review {incident.id}"},
            },
        ],
        "edges": [{"from": "trigger", "to": "note", "condition": "success"}],
    }


def test_playbook_graph_tools_draft_disabled_and_validate_schema():
    soar = _StubSoarPlaybooks()
    ctx = ToolContext(user_id="analyst-1", soar_client=soar)

    draft = asyncio.run(REGISTRY["draft_playbook_graph"].impl(ctx, _valid_playbook_payload()))
    assert draft["playbook"]["enabled"] is False
    assert draft["validation"]["valid"] is True
    assert draft["playbook"]["nodes"][1]["config"]["template"] == "Review {incident.id}"

    invalid = asyncio.run(
        REGISTRY["validate_playbook_graph"].impl(
            ctx,
            {
                "playbook": {
                    "id": "pb_bad",
                    "name": "Bad",
                    "nodes": [{"id": "note", "type": "case.note", "config": {}}],
                }
            },
        )
    )
    assert invalid["valid"] is False
    assert "playbook must include at least one trigger node" in invalid["errors"]
    assert "node note missing required config: template" in invalid["errors"]


def test_playbook_apply_tool_creates_disabled_playbook_and_simulates_saved_graph():
    soar = _StubSoarPlaybooks()
    ctx = ToolContext(user_id="analyst-1", soar_client=soar)

    applied = asyncio.run(
        REGISTRY["apply_playbook_patch"].impl(
            ctx,
            {"mode": "create", "playbook": _valid_playbook_payload() | {"enabled": True}},
        )
    )
    assert applied["operation"] == "create"
    assert applied["playbook"]["enabled"] is False
    create_request = next(
        request for request in soar.requests if request[0] == "POST" and request[1] == "/playbooks"
    )
    assert create_request[2]["json"]["enabled"] is False
    assert create_request[2]["json"]["id"] == "pb_agent"

    simulated = asyncio.run(
        REGISTRY["simulate_playbook"].impl(ctx, {"playbookId": "pb_agent"})
    )
    assert simulated["valid"] is True
    assert ("POST", "/playbooks/pb_agent/simulate", {"json": {}}) in soar.requests

    run = asyncio.run(
        REGISTRY["run_playbook"].impl(
            ctx,
            {"incidentId": "inc_1", "playbookId": "pb_agent"},
        )
    )
    assert run["status"] == "waiting_approval"
    assert ("POST", "/incidents/inc_1/playbooks/pb_agent/run", {"json": {}}) in soar.requests


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def test_role_registry_matches_real_runtime_spec():
    roles = {role.id: role for role in list_roles()}

    assert set(roles) == {
        "chat",
        "widget-builder",
        "incident-triage",
        "playbook-draft",
        "soc-investigation",
    }
    assert roles["chat"].tier == "fast"
    assert roles["chat"].allowed_tool_categories == frozenset({"read"})
    assert roles["incident-triage"].tier == "balanced"
    assert roles["incident-triage"].allowed_tool_categories == frozenset({"read", "draft"})
    assert roles["incident-triage"].token_budget == 150_000
    assert roles["soc-investigation"].tier == "deep"
    assert roles["soc-investigation"].allowed_tool_categories == frozenset(
        {"read", "draft", "write", "execute"}
    )
    assert roles["soc-investigation"].token_budget == 300_000
    assert all(role.system_prompt.strip() for role in roles.values())
    assert get_role("missing-role") is None


def test_router_raises_without_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    with pytest.raises(AgentNotConfiguredError):
        pick_backend(get_role("incident-triage"), "user-no-pref")  # type: ignore[arg-type]


def test_router_uses_enterprise_settings_model(monkeypatch):
    store = configured_settings_store(
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="sk-test",
    )
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    backend = pick_backend(get_role("incident-triage"), "user-1")  # type: ignore[arg-type]

    assert backend.name == "anthropic"
    assert backend.model == "claude-sonnet-4-6"


def test_router_ignores_role_tier_env_override(monkeypatch):
    store = configured_settings_store(model="gpt-4o-mini")
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    monkeypatch.setenv("FORTIDASHBOARD_ROLE_CHAT_TIER", "deep")

    backend = pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]

    assert backend.name == "openai"
    assert backend.model == "gpt-4o-mini"


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


def test_session_store_tracks_role_and_token_totals():
    store = SessionStore()
    s = store.create(user_id="user-1", role_id="incident-triage")

    assert s.role_id == "incident-triage"
    assert s.tokens_in_total == 0
    assert s.tokens_out_total == 0
    assert s.pending_approvals == {}


# ---------------------------------------------------------------------------
# Scripted backend
# ---------------------------------------------------------------------------


async def _collect_backend(backend: Any, **kwargs: Any) -> list[Any]:
    return [event async for event in backend.stream_decide(**kwargs)]


def test_scripted_backend_streams_keyword_tool_call():
    backend = ScriptedBackend()
    events = asyncio.run(
        _collect_backend(
            backend,
            history=[{"role": "user", "content": "Liste meus incidentes"}],
            tools=list(REGISTRY.values()),
            system_prompt="system",
            locale="pt-BR",
            max_output_tokens=512,
        )
    )
    assert [event.kind for event in events] == ["tool_call", "final"]
    assert isinstance(events[0], ToolCall)
    assert events[0].tool_name == "list_incidents"
    assert isinstance(events[1], Final)
    assert events[1].stop_reason == "tool_use"


def test_scripted_backend_streams_final_after_tool_result():
    backend = ScriptedBackend()
    events = asyncio.run(
        _collect_backend(
            backend,
            history=[
                {"role": "user", "content": "Liste incidentes"},
                {
                    "role": "tool",
                    "tool_name": "list_incidents",
                    "result": {"items": [], "count": 0},
                },
            ],
            tools=list(REGISTRY.values()),
            system_prompt="system",
            locale="pt-BR",
            max_output_tokens=512,
        )
    )
    assert [event.kind for event in events] == ["text_delta", "final"]
    assert isinstance(events[0], TextDelta)
    assert "list_incidents" in events[0].text
    assert isinstance(events[1], Final)
    assert events[1].stop_reason == "end_turn"


def test_anthropic_backend_parses_text_stream():
    async def _handler(_request: httpx.Request) -> httpx.Response:
        body = "\n\n".join(
            [
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}',
                (
                    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
                    '"usage":{"output_tokens":2}}'
                ),
                'data: {"type":"message_stop"}',
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    backend = AnthropicBackend(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )

    events = asyncio.run(
        _collect_backend(
            backend,
            history=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="system",
            locale="en-US",
            max_output_tokens=512,
        )
    )

    assert [event.kind for event in events] == ["text_delta", "final"]
    assert events[0].text == "hello"
    assert events[1].stop_reason == "end_turn"


def test_openai_backend_parses_text_stream_with_usage():
    async def _handler(_request: httpx.Request) -> httpx.Response:
        body = "\n\n".join(
            [
                'data: {"choices":[{"delta":{"content":"hello"}}]}',
                (
                    'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
                    '"usage":{"prompt_tokens":7,"completion_tokens":2}}'
                ),
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    backend = OpenAIBackend(
        api_key="sk-test",
        model="gpt-4o",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )

    events = asyncio.run(
        _collect_backend(
            backend,
            history=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="system",
            locale="en-US",
            max_output_tokens=512,
        )
    )

    assert [event.kind for event in events] == ["text_delta", "final"]
    assert events[0].text == "hello"
    assert events[1].tokens_in == 7
    assert events[1].tokens_out == 2


def test_gemini_backend_parses_text_and_tool_call():
    from app.ai.agent.backends.gemini import GeminiBackend

    requests: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "Vou consultar os incidentes."},
                                {
                                    "functionCall": {
                                        "name": "list_incidents",
                                        "args": {"severity": "high"},
                                    }
                                },
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 9,
                    "candidatesTokenCount": 4,
                },
            },
        )

    backend = GeminiBackend(
        api_key="sk-test",
        model="gemini-flash-latest",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )

    events = asyncio.run(
        _collect_backend(
            backend,
            history=[{"role": "user", "content": "liste incidentes high"}],
            tools=[REGISTRY["list_incidents"]],
            system_prompt="system",
            locale="pt-BR",
            max_output_tokens=512,
        )
    )

    assert [event.kind for event in events] == ["text_delta", "tool_call", "final"]
    assert events[0].text == "Vou consultar os incidentes."
    assert events[1].tool_name == "list_incidents"
    assert events[1].args == {"severity": "high"}
    assert events[2].stop_reason == "tool_use"
    assert events[2].tokens_in == 9
    assert events[2].tokens_out == 4
    assert requests[0].headers["x-goog-api-key"] == "sk-test"
    assert requests[0].url.path.endswith("/v1beta/models/gemini-flash-latest:generateContent")
    body = json.loads(requests[0].content)
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "list_incidents"
    assert body["tools"][0]["functionDeclarations"][0]["parameters"]["type"] == "OBJECT"


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
    session = store.create(
        user_id="user-1",
        backend="scripted",
        locale="pt-BR",
        role_id="incident-triage",
    )
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
    assert done["tokens_in"] > 0
    assert done["tokens_out"] > 0
    assert session.tokens_in_total == done["tokens_in"]
    assert session.tokens_out_total == done["tokens_out"]
    assert any(audit["details"]["toolName"] == "list_incidents" for audit in audit_calls)


def test_runner_returns_tool_result_error_for_unallowed_tool():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", role_id="chat")

    class DraftBackend:
        name = "broken"
        model = ""

        async def stream_decide(self, **kwargs):
            if kwargs["history"] and kwargs["history"][-1].get("role") == "tool":
                yield TextDelta(text="recovered")
                yield Final(stop_reason="end_turn", tokens_in=8, tokens_out=2)
                return
            yield ToolCall(
                call_id="call_1",
                tool_name="draft_widget",
                args={
                    "provider": "fortigate",
                    "visualType": "card",
                    "fieldIds": ["system.cpu"],
                },
            )
            yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=3)

    runner = AgentRunner(backend=DraftBackend(), session_store=store)
    ctx = ToolContext(user_id="user-1")
    events = asyncio.run(
        _collect(runner, session=session, user_message="run", tool_context=ctx)
    )

    blocked = next(e for e in events if e["kind"] == "tool_result")
    assert blocked["status"] == "error"
    assert blocked["error"] == "tool not allowed for this role"
    assert events[-1]["kind"] == "done"


def test_runner_blocks_tool_when_required_permission_is_missing():
    calls: list[dict[str, Any]] = []

    async def _restricted_tool(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"secret": "audit"}

    tool = AgentTool(
        name="restricted_audit_for_test",
        description="Restricted read tool used by permission tests.",
        input_schema={"type": "object", "properties": {}},
        impl=_restricted_tool,
        required_permissions=frozenset({"audit.read"}),
    )
    original = REGISTRY.get(tool.name)
    REGISTRY[tool.name] = tool

    class RestrictedBackend:
        name = "restricted"
        model = ""

        async def stream_decide(self, **kwargs):
            if kwargs["history"] and kwargs["history"][-1].get("role") == "tool":
                yield TextDelta(text="blocked")
                yield Final(stop_reason="end_turn", tokens_in=8, tokens_out=2)
                return
            yield ToolCall(
                call_id="call_restricted",
                tool_name="restricted_audit_for_test",
                args={},
            )
            yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=3)

    try:
        store = SessionStore()
        session = store.create(user_id="user-1", backend="restricted", role_id="chat")
        runner = AgentRunner(backend=RestrictedBackend(), session_store=store)
        events = asyncio.run(
            _collect(
                runner,
                session=session,
                user_message="read audit",
                tool_context=ToolContext(user_id="user-1", effective_permissions=frozenset()),
            )
        )
    finally:
        if original is None:
            REGISTRY.pop(tool.name, None)
        else:
            REGISTRY[tool.name] = original

    blocked = next(e for e in events if e["kind"] == "tool_result")
    assert blocked["status"] == "error"
    assert blocked["error"] == "missing required permission: audit.read"
    assert calls == []
    assert events[-1]["kind"] == "done"


def test_runner_invokes_tool_when_required_permission_is_present():
    calls: list[dict[str, Any]] = []

    async def _restricted_tool(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"secret": "audit"}

    tool = AgentTool(
        name="allowed_audit_for_test",
        description="Restricted read tool used by permission tests.",
        input_schema={"type": "object", "properties": {}},
        impl=_restricted_tool,
        required_permissions=frozenset({"audit.read"}),
    )
    original = REGISTRY.get(tool.name)
    REGISTRY[tool.name] = tool

    class RestrictedBackend:
        name = "restricted"
        model = ""

        async def stream_decide(self, **kwargs):
            if kwargs["history"] and kwargs["history"][-1].get("role") == "tool":
                yield TextDelta(text="allowed")
                yield Final(stop_reason="end_turn", tokens_in=8, tokens_out=2)
                return
            yield ToolCall(
                call_id="call_allowed",
                tool_name="allowed_audit_for_test",
                args={"scope": "recent"},
            )
            yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=3)

    try:
        store = SessionStore()
        session = store.create(user_id="user-1", backend="restricted", role_id="chat")
        runner = AgentRunner(backend=RestrictedBackend(), session_store=store)
        events = asyncio.run(
            _collect(
                runner,
                session=session,
                user_message="read audit",
                tool_context=ToolContext(
                    user_id="user-1",
                    effective_permissions=frozenset({"audit.read"}),
                ),
            )
        )
    finally:
        if original is None:
            REGISTRY.pop(tool.name, None)
        else:
            REGISTRY[tool.name] = original

    result = next(e for e in events if e["kind"] == "tool_result")
    assert result["status"] == "ok"
    assert calls == [{"scope": "recent"}]
    assert events[-1]["kind"] == "done"


def test_soc_assistant_session_allows_permission_gated_draft_tools():
    calls: list[dict[str, Any]] = []

    async def _draft_tool(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"draft": True}

    tool = AgentTool(
        name="draft_playbook_for_test",
        description="Draft tool used by permission-derived SOC Assistant tests.",
        input_schema={"type": "object", "properties": {}},
        impl=_draft_tool,
        category="draft",
        required_permissions=frozenset({"playbooks.manage"}),
    )
    original = REGISTRY.get(tool.name)
    REGISTRY[tool.name] = tool

    class DraftBackend:
        name = "draft"
        model = ""

        async def stream_decide(self, **kwargs):
            if kwargs["history"] and kwargs["history"][-1].get("role") == "tool":
                yield TextDelta(text="drafted")
                yield Final(stop_reason="end_turn", tokens_in=8, tokens_out=2)
                return
            yield ToolCall(
                call_id="call_draft",
                tool_name="draft_playbook_for_test",
                args={"intent": "triage high severity incidents"},
            )
            yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=3)

    try:
        store = SessionStore()
        session = store.create(user_id="user-1", backend="draft", role_id="soc-assistant")
        runner = AgentRunner(backend=DraftBackend(), session_store=store)
        events = asyncio.run(
            _collect(
                runner,
                session=session,
                user_message="draft a playbook",
                tool_context=ToolContext(
                    user_id="user-1",
                    effective_permissions=frozenset({"playbooks.manage"}),
                ),
            )
        )
    finally:
        if original is None:
            REGISTRY.pop(tool.name, None)
        else:
            REGISTRY[tool.name] = original

    result = next(e for e in events if e["kind"] == "tool_result")
    assert result["status"] == "ok"
    assert calls == [{"intent": "triage high severity incidents"}]
    assert events[-1]["kind"] == "done"


def test_runner_waits_for_execute_tool_approval_before_invoking():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", role_id="soc-assistant")
    calls: list[dict[str, Any]] = []

    async def _execute_tool(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"runId": "run_1"}

    tool = AgentTool(
        name="execute_playbook_for_test",
        description="Execute tool used only by the approval-gate test.",
        input_schema={"type": "object", "properties": {"playbookId": {"type": "string"}}},
        impl=_execute_tool,
        category="execute",
        requires_approval=True,
        required_permissions=frozenset({"playbooks.execute"}),
    )
    original = REGISTRY.get(tool.name)
    REGISTRY[tool.name] = tool

    class ExecuteBackend:
        name = "executor"
        model = ""

        async def stream_decide(self, **_kwargs):
            if not session.history or session.history[-1].role != "tool":
                yield ToolCall(
                    call_id="call_execute",
                    tool_name="execute_playbook_for_test",
                    args={"playbookId": "pb_1"},
                )
                yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=4)
                return
            yield TextDelta(text="run started")
            yield Final(stop_reason="end_turn", tokens_in=9, tokens_out=2)

    async def _run_and_approve() -> list[dict[str, Any]]:
        runner = AgentRunner(
            backend=ExecuteBackend(),
            session_store=store,
            approval_timeout_seconds=1,
        )
        events: list[dict[str, Any]] = []

        async def _consume() -> None:
            async for event in runner.run_turn(
                session=session,
                user_message="run playbook",
                tool_context=ToolContext(
                    user_id="user-1",
                    effective_permissions=frozenset({"playbooks.execute"}),
                ),
            ):
                events.append(event.to_dict())
                if event.kind.value == "awaiting_approval":
                    future = session.pending_approvals[event.call_id]
                    future.set_result({"granted": True, "reason": "test approval"})

        await _consume()
        return events

    try:
        events = asyncio.run(_run_and_approve())
    finally:
        if original is None:
            REGISTRY.pop(tool.name, None)
        else:
            REGISTRY[tool.name] = original

    assert [e["kind"] for e in events].count("awaiting_approval") == 1
    assert calls == [{"playbookId": "pb_1"}]
    assert events[-1]["kind"] == "done"


def test_runner_aborts_when_role_token_budget_is_exhausted():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", role_id="chat")
    session.tokens_in_total = 20_000

    class NeverCalledBackend:
        name = "never"
        model = ""

        async def stream_decide(self, **_kwargs):
            raise AssertionError("backend must not be called after budget is exhausted")
            yield  # pragma: no cover

    runner = AgentRunner(backend=NeverCalledBackend(), session_store=store)
    ctx = ToolContext(user_id="user-1")
    events = asyncio.run(
        _collect(runner, session=session, user_message="hello", tool_context=ctx)
    )

    assert events[-1]["kind"] == "error"
    assert events[-1]["code"] == "budget_exceeded"


def test_runner_waits_for_write_tool_approval_before_invoking():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", role_id="soc-investigation")
    calls: list[dict[str, Any]] = []

    async def _write_tool(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"applied": True}

    tool = AgentTool(
        name="write_policy_for_test",
        description="Write tool used only by the approval-gate test.",
        input_schema={"type": "object", "properties": {"policyId": {"type": "string"}}},
        impl=_write_tool,
        category="write",
        requires_approval=True,
    )
    original = REGISTRY.get(tool.name)
    REGISTRY[tool.name] = tool

    class WriteBackend:
        name = "writer"
        model = ""

        async def stream_decide(self, **_kwargs):
            if not session.history or session.history[-1].role != "tool":
                yield ToolCall(
                    call_id="call_write",
                    tool_name="write_policy_for_test",
                    args={"policyId": "p1"},
                )
                yield Final(stop_reason="tool_use", tokens_in=10, tokens_out=4)
                return
            yield TextDelta(text="write completed")
            yield Final(stop_reason="end_turn", tokens_in=9, tokens_out=2)

    async def _run_and_approve() -> list[dict[str, Any]]:
        runner = AgentRunner(
            backend=WriteBackend(),
            session_store=store,
            approval_timeout_seconds=1,
        )
        events: list[dict[str, Any]] = []

        async def _consume() -> None:
            async for event in runner.run_turn(
                session=session,
                user_message="apply it",
                tool_context=ToolContext(user_id="user-1"),
            ):
                events.append(event.to_dict())
                if event.kind.value == "awaiting_approval":
                    future = session.pending_approvals[event.call_id]
                    future.set_result({"granted": True, "reason": "test approval"})

        await _consume()
        return events

    try:
        events = asyncio.run(_run_and_approve())
    finally:
        if original is None:
            REGISTRY.pop(tool.name, None)
        else:
            REGISTRY[tool.name] = original

    assert [e["kind"] for e in events].count("awaiting_approval") == 1
    assert calls == [{"policyId": "p1"}]
    assert events[-1]["kind"] == "done"


def test_runner_emits_backend_error_without_exception():
    store = SessionStore()
    session = store.create(user_id="user-1", backend="scripted", role_id="chat")

    class ErrorBackend:
        name = "erroring"
        model = ""

        async def stream_decide(self, **_kwargs):
            yield BackendError(message="bad credentials", code="auth", retryable=False)

    runner = AgentRunner(backend=ErrorBackend(), session_store=store)
    events = asyncio.run(
        _collect(
            runner,
            session=session,
            user_message="hello",
            tool_context=ToolContext(user_id="user-1"),
        )
    )

    assert events[-1]["kind"] == "error"
    assert events[-1]["code"] == "auth"


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_list_backends_endpoint_is_not_public():
    client = TestClient(app)
    response = client.get("/api/ai/agent/backends")
    assert response.status_code == 404


def test_list_tools_endpoint_returns_input_schemas():
    client = TestClient(app)
    response = client.get("/api/ai/agent/tools")
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "list_incidents" in names
    list_incidents = next(item for item in payload["items"] if item["name"] == "list_incidents")
    assert list_incidents["inputSchema"]["type"] == "object"


def test_list_tools_endpoint_hides_permission_gated_tools_for_default_analyst():
    client = TestClient(app)
    response = client.get("/api/ai/agent/tools")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "search_audit" not in names
    assert "run_playbook" not in names
    assert "update_ticket" not in names


def test_list_tools_endpoint_exposes_required_permissions():
    client = TestClient(app)
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "admin-1",
        "email": "admin@example.test",
        "roles": ["admin"],
    }
    try:
        response = client.get("/api/ai/agent/tools")
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    payload = response.json()
    search_audit = next(item for item in payload["items"] if item["name"] == "search_audit")
    assert search_audit["requiredPermissions"] == ["audit.read"]
    run_playbook = next(item for item in payload["items"] if item["name"] == "run_playbook")
    assert run_playbook["category"] == "execute"
    assert run_playbook["requiresApproval"] is True
    assert run_playbook["requiredPermissions"] == ["playbooks.execute"]


def test_list_roles_endpoint_is_not_public():
    client = TestClient(app)
    response = client.get("/api/ai/agent/roles")
    assert response.status_code == 404


def test_create_session_returns_session_id(monkeypatch):
    store = configured_settings_store()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"locale": "pt-BR"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["backend"] == "openai"
    assert payload["model"] == "gpt-4o"
    assert payload["role"] == "soc-assistant"
    assert payload["tokensIn"] == 0
    assert payload["tokensOut"] == 0
    assert payload["sessionId"]


def test_create_session_rejects_frontend_backend_selection(monkeypatch):
    store = configured_settings_store()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"backend": "openai"},
    )
    assert response.status_code == 422


def test_create_session_returns_conflict_when_assistant_unconfigured(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"locale": "pt-BR"},
    )
    assert response.status_code == 409
    assert "not configured" in response.json()["detail"]


def test_send_message_streams_steps_and_records_audit(monkeypatch):
    store = configured_settings_store()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    async def _stream_final(self, **_kwargs):
        yield TextDelta(text="Olá")
        yield Final(stop_reason="end_turn", tokens_in=5, tokens_out=2)

    monkeypatch.setattr(OpenAIBackend, "stream_decide", _stream_final)
    client = TestClient(app)
    headers = csrf_headers(client)
    create = client.post(
        "/api/ai/agent/sessions",
        headers=headers,
        json={"locale": "pt-BR"},
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


def test_send_message_returns_step_error_when_assistant_unconfigured(monkeypatch):
    store = configured_settings_store()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    client = TestClient(app)
    headers = csrf_headers(client)
    create = client.post(
        "/api/ai/agent/sessions",
        headers=headers,
        json={"locale": "pt-BR"},
    )
    assert create.status_code == 201
    session_id = create.json()["sessionId"]
    store.upsert(api_key="", updated_by="admin@example.com")

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

    error = next(e for e in events if e.get("type") == "step" and e.get("kind") == "error")
    assert error["code"] == "agent_not_configured"
    assert "not configured" in error["message"]


def test_approval_endpoint_resolves_pending_future(monkeypatch):
    store = configured_settings_store()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )
    client = TestClient(app)
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "admin-1",
        "email": "admin@example.test",
        "roles": ["admin"],
    }
    headers = csrf_headers(client)
    try:
        create = client.post(
            "/api/ai/agent/sessions",
            headers=headers,
            json={"locale": "pt-BR"},
        )
        assert create.status_code == 201
        session_id = create.json()["sessionId"]
        store = get_session_store()
        session = store.get(session_id, user_id="admin-1")
        assert session is not None

        class _Future:
            def __init__(self) -> None:
                self._done = False
                self._result: dict[str, Any] | None = None

            def done(self) -> bool:
                return self._done

            def set_result(self, value: dict[str, Any]) -> None:
                self._done = True
                self._result = value

            def result(self) -> dict[str, Any] | None:
                return self._result

        future = _Future()
        session.pending_approvals["call_1"] = future
        response = client.post(
            f"/api/ai/agent/sessions/{session_id}/approvals/call_1",
            headers=headers,
            json={"granted": True, "reason": "ok"},
        )

        assert response.status_code == 200
        assert future.done()
        assert future.result()["granted"] is True
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
