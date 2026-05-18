from __future__ import annotations

from datetime import UTC, datetime

from app.ai.agent.settings import (
    AiAgentSettings,
    InMemoryAiAgentSettingsStore,
)


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
