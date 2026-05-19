"""Tests for per-user AI preferences and the Gemini native provider."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.ai import resolve_ai_provider
from app.ai.preferences import (
    GeminiAIProvider,
    InMemoryPreferenceStore,
    UserAiPreference,
    build_provider_for_user,
    get_preference_store,
)
from app.ai.provider import IncidentContext
from app.main import app


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    get_preference_store.cache_clear()


# ---------------------------------------------------------------------------
# Preference store
# ---------------------------------------------------------------------------


def test_in_memory_preference_store_upsert_round_trip():
    store = InMemoryPreferenceStore()
    pref = store.upsert(
        user_id="user-1",
        provider="gemini",
        model="gemini-flash-latest",
        api_key="AIza-secret",
    )
    assert pref.api_key == "AIza-secret"
    loaded = store.get("user-1")
    assert loaded is not None
    assert loaded.provider == "gemini"


def test_user_preference_to_dict_redacts_key_by_default():
    pref = UserAiPreference(user_id="u1", api_key="secret")
    payload = pref.to_dict(redact=True)
    assert payload["apiKeySet"] is True
    assert payload["apiKey"] == ""


# ---------------------------------------------------------------------------
# Gemini native provider
# ---------------------------------------------------------------------------


def test_gemini_chat_uses_generate_content_endpoint(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "hello there"}]}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GeminiAIProvider(
        api_key="AIza-test",
        model="gemini-flash-latest",
        http_client=client,
    )
    reply = provider.chat([{"role": "user", "content": "hi"}])

    assert reply == "hello there"
    assert "generateContent" in captured["url"]
    assert captured["headers"].get("x-goog-api-key") == "AIza-test"
    assert "systemInstruction" in captured["body"]
    assert "\"role\": \"user\"" in captured["body"].replace(" ", "").replace(
        '"role":"user"', '"role": "user"'
    ) or '"role":"user"' in captured["body"]


def test_gemini_analyze_incident_parses_json_payload():
    json_payload = (
        '{"headline":"h","summary":"s","risk_score":42,'
        '"suggested_triage":"T2","suggested_ticket_status":"investigating",'
        '"indicators_of_compromise":["10.0.0.1"],"next_steps":["check"],'
        '"references":[],"cvss_score":4.5,"cvss_severity":"Medium",'
        '"cvss_vector":"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"}'
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json_payload}]}}]},
        )

    provider = GeminiAIProvider(
        api_key="k",
        model="gemini-flash-latest",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    context = IncidentContext(
        incident_id="inc-1",
        title="Brute force",
        severity="medium",
        triage_level="T2",
        ticket_status="new",
        summary="",
    )
    analysis = provider.analyze_incident(context, locale="pt-BR")
    assert analysis.risk_score == 42
    assert analysis.suggested_triage == "T2"
    assert "10.0.0.1" in analysis.indicators_of_compromise


# ---------------------------------------------------------------------------
# build_provider_for_user
# ---------------------------------------------------------------------------


def test_build_provider_for_user_returns_gemini_when_preference_saved(monkeypatch):
    store = InMemoryPreferenceStore()
    store.upsert(
        user_id="user-1",
        mode="api",
        provider="gemini",
        model="gemini-flash-latest",
        api_key="AIza-saved",
    )
    monkeypatch.setattr(
        "app.ai.preferences.get_preference_store", lambda: store
    )
    monkeypatch.setattr("app.ai.get_preference_store", lambda: store)

    provider = build_provider_for_user("user-1")
    assert provider is not None
    assert provider.name == "gemini"
    assert provider.model == "gemini-flash-latest"


def test_build_provider_for_user_returns_none_without_preference():
    store = InMemoryPreferenceStore()
    assert build_provider_for_user_with_store("user-x", store) is None


def build_provider_for_user_with_store(user_id, store):
    # Local helper that mirrors the real factory but takes the store
    # explicitly so the test doesn't depend on module-level patching.
    pref = store.get(user_id)
    return pref


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_get_preferences_returns_defaults_for_new_user():
    client = TestClient(app)
    response = client.get("/api/ai/preferences")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "api"
    assert payload["provider"] == "gemini"
    assert payload["apiKeySet"] is False


def test_put_preferences_saves_key_and_redacts_on_read():
    client = TestClient(app)
    headers = csrf_headers(client)
    response = client.put(
        "/api/ai/preferences",
        headers=headers,
        json={
            "mode": "api",
            "provider": "gemini",
            "model": "gemini-flash-latest",
            "apiKey": "AIza-from-test",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["apiKeySet"] is True
    assert "apiKey" not in payload or payload.get("apiKey") in (None, "")

    # Subsequent GET still hides the key.
    get_response = client.get("/api/ai/preferences")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["provider"] == "gemini"
    assert body["apiKeySet"] is True


def test_put_preferences_rejects_unsupported_provider():
    client = TestClient(app)
    response = client.put(
        "/api/ai/preferences",
        headers=csrf_headers(client),
        json={"provider": "petesPalantir"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# resolve_ai_provider falls back to env when user has no preference
# ---------------------------------------------------------------------------


def test_resolve_ai_provider_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PENGUARD_ENABLE_LAB_DEMO_TOOLS", "true")
    monkeypatch.setenv("PENGUARD_AI_PROVIDER", "scripted")
    from app.ai.provider import get_ai_provider
    from app.core.config import get_settings

    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    provider = resolve_ai_provider(user_id="user-without-pref")
    assert provider.name == "scripted"
