from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.ai.agent.backends.base import BackendError, Final, TextDelta
from app.ai.agent.roles import get_role
from app.ai.agent.router import AgentNotConfiguredError, pick_backend
from app.ai.agent.settings import (
    AiAgentSettings,
    InMemoryAiAgentSettingsStore,
    get_ai_agent_settings_store,
)
from app.auth import dependencies as auth_dependencies
from app.main import app

ADMIN_USER = {"id": "usr_admin", "email": "admin@example.com", "roles": ["admin"]}


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def override_user(user: dict):
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: user


def teardown_function():
    get_ai_agent_settings_store.cache_clear()
    auth_dependencies.get_auth_audit_store.cache_clear()
    app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)


def test_in_memory_ai_agent_settings_round_trip_redacts_key():
    store = InMemoryAiAgentSettingsStore()

    saved = store.upsert(
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="sk-ant-secret",
        updated_by="admin@example.com",
    )
    loaded = store.get()

    assert loaded is not None
    assert saved.provider == "anthropic"
    assert loaded.model == "claude-sonnet-4-6"
    assert loaded.api_key == "sk-ant-secret"
    assert loaded.api_key_set is True
    public = loaded.to_dict(redact=True)
    assert public["apiKeySet"] is True
    assert "apiKey" not in public
    assert public["provider"] == "anthropic"


def test_in_memory_ai_agent_settings_clear_key_keeps_provider_and_model():
    store = InMemoryAiAgentSettingsStore()
    store.upsert(
        provider="openai",
        model="gpt-4o",
        api_key="sk-openai-secret",
        updated_by="admin@example.com",
    )

    updated = store.upsert(api_key="", updated_by="admin@example.com")

    assert updated.provider == "openai"
    assert updated.model == "gpt-4o"
    assert updated.api_key == ""
    assert updated.api_key_set is False


def test_ai_agent_settings_to_dict_formats_timestamps():
    settings = AiAgentSettings(
        provider="openai",
        model="gpt-4o",
        api_key="sk",
        last_tested_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        last_test_status="success",
        updated_by="admin@example.com",
        updated_at=datetime(2026, 5, 18, 12, 1, tzinfo=UTC),
    )

    payload = settings.to_dict(redact=True)

    assert payload["lastTestedAt"] == "2026-05-18T12:00:00.000Z"
    assert payload["updatedAt"] == "2026-05-18T12:01:00.000Z"
    assert payload["lastTestStatus"] == "success"


def test_agent_router_uses_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    store.upsert(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test",
        updated_by="admin@example.com",
    )
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    backend = pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]

    assert backend.name == "openai"
    assert backend.model == "gpt-4o"


def test_agent_router_uses_gemini_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    store.upsert(
        provider="gemini",
        model="gemini-flash-latest",
        api_key="sk-test",
        updated_by="admin@example.com",
    )
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    backend = pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]

    assert backend.name == "gemini"
    assert backend.model == "gemini-flash-latest"


def test_agent_router_raises_without_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    monkeypatch.setattr(
        "app.ai.agent.router.get_ai_agent_settings_store",
        lambda: store,
    )

    with pytest.raises(AgentNotConfiguredError):
        pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]


def test_get_ai_agent_settings_requires_permission():
    client = TestClient(app)

    response = client.get("/api/ai/agent/settings")

    assert response.status_code == 403


def test_admin_can_save_and_read_ai_agent_settings_redacted():
    auth_dependencies.get_auth_audit_store.cache_clear()
    override_user(ADMIN_USER)
    client = TestClient(app)
    headers = csrf_headers(client)

    response = client.put(
        "/api/ai/agent/settings",
        headers=headers,
        json={
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "apiKey": "sk-ant-secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "anthropic"
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["apiKeySet"] is True
    assert payload["configured"] is True
    assert "apiKey" not in payload

    get_response = client.get("/api/ai/agent/settings")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["apiKeySet"] is True
    assert "apiKey" not in body

    update_audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.settings.updated"
    )
    read_audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.settings.read"
    )
    assert update_audit["items"][0]["actor"] == {
        "id": "usr_admin",
        "email": "admin@example.com",
    }
    assert update_audit["items"][0]["details"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "credentialSet": True,
    }
    assert read_audit["items"][0]["details"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "credentialSet": True,
        "configured": True,
    }
    assert "sk-ant-secret" not in str(update_audit["items"][0]["details"])
    assert "apiKey" not in str(update_audit["items"][0]["details"])


def test_update_ai_agent_settings_accepts_gemini_provider():
    override_user(ADMIN_USER)
    client = TestClient(app)

    response = client.put(
        "/api/ai/agent/settings",
        headers=csrf_headers(client),
        json={"provider": "gemini", "model": "gemini-flash-latest", "apiKey": "k"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gemini"
    assert payload["model"] == "gemini-flash-latest"
    assert payload["apiKeySet"] is True
    assert payload["configured"] is True


def test_update_ai_agent_settings_rejects_overlong_key_without_echoing_secret():
    override_user(ADMIN_USER)
    client = TestClient(app)
    secret = "s" * 1100

    response = client.put(
        "/api/ai/agent/settings",
        headers=csrf_headers(client),
        json={"provider": "openai", "model": "gpt-4o", "apiKey": secret},
    )

    assert response.status_code == 400
    assert "apiKey" in response.json()["detail"]
    assert secret not in response.text


def test_update_ai_agent_settings_rejects_non_string_key_without_echoing_secret():
    override_user(ADMIN_USER)
    client = TestClient(app)
    secret = "sk-super-secret"

    response = client.put(
        "/api/ai/agent/settings",
        headers=csrf_headers(client),
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "apiKey": {"secret": secret},
        },
    )

    assert response.status_code == 400
    assert "apiKey" in response.json()["detail"]
    assert secret not in response.text


def test_update_ai_agent_settings_rejects_array_body_without_echoing_secret():
    override_user(ADMIN_USER)
    client = TestClient(app)
    secret = "sk-secret-in-nonstring-key"

    response = client.put(
        "/api/ai/agent/settings",
        headers=csrf_headers(client),
        json=[
            {
                "provider": "openai",
                "model": "gpt-4o",
                "apiKey": {"secret": secret},
            }
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "settings payload must be an object"
    assert secret not in response.text


def test_test_ai_agent_settings_marks_missing_config_failure():
    auth_dependencies.get_auth_audit_store.cache_clear()
    override_user(ADMIN_USER)
    client = TestClient(app)

    response = client.post("/api/ai/agent/settings/test", headers=csrf_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "not_configured"

    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.settings.tested"
    )
    assert audit["items"][0]["details"] == {
        "provider": "",
        "model": "",
        "credentialSet": False,
        "configured": False,
        "status": "not_configured",
    }


def test_test_ai_agent_settings_calls_provider_probe_success(monkeypatch):
    override_user(ADMIN_USER)
    client = TestClient(app)
    headers = csrf_headers(client)
    client.put(
        "/api/ai/agent/settings",
        headers=headers,
        json={"provider": "openai", "model": "gpt-4o", "apiKey": "sk-openai-secret"},
    )
    calls = []

    async def _probe(self, **kwargs):
        calls.append({"model": self.model, **kwargs})
        yield TextDelta(text="OK")
        yield Final(stop_reason="end_turn", tokens_in=5, tokens_out=1)

    monkeypatch.setattr("app.ai.agent.backends.openai.OpenAIBackend.stream_decide", _probe)

    response = client.post("/api/ai/agent/settings/test", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "success"
    assert payload["error"] is None
    assert calls
    assert calls[0]["model"] == "gpt-4o"
    assert calls[0]["tools"] == []
    settings = get_ai_agent_settings_store().get()
    assert settings is not None
    assert settings.last_test_status == "success"
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.settings.tested"
    )
    assert audit["items"][0]["details"] == {
        "provider": "openai",
        "model": "gpt-4o",
        "credentialSet": True,
        "configured": True,
        "status": "success",
    }


def test_test_ai_agent_settings_persists_provider_probe_failure(monkeypatch):
    override_user(ADMIN_USER)
    client = TestClient(app)
    headers = csrf_headers(client)
    secret = "sk-openai-secret"
    client.put(
        "/api/ai/agent/settings",
        headers=headers,
        json={"provider": "openai", "model": "gpt-4o", "apiKey": secret},
    )

    async def _probe(_self, **_kwargs):
        yield BackendError(message="OpenAI auth failed", code="auth", retryable=False)

    monkeypatch.setattr("app.ai.agent.backends.openai.OpenAIBackend.stream_decide", _probe)

    response = client.post("/api/ai/agent/settings/test", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert payload["error"] == "OpenAI auth failed"
    assert secret not in response.text
    settings = get_ai_agent_settings_store().get()
    assert settings is not None
    assert settings.last_test_status == "failed"
    assert settings.last_test_error == "OpenAI auth failed"
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.agent.settings.tested"
    )
    assert audit["items"][0]["details"] == {
        "provider": "openai",
        "model": "gpt-4o",
        "credentialSet": True,
        "configured": True,
        "status": "failed",
    }
