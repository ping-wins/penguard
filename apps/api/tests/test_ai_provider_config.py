import pytest

from app.ai.provider import AIConfigurationError, get_ai_provider
from app.core.config import get_settings


def teardown_function():
    get_settings.cache_clear()
    get_ai_provider.cache_clear()


def test_default_ai_provider_is_not_scripted_without_lab_mode(monkeypatch):
    monkeypatch.delenv("PENGUARD_AI_PROVIDER", raising=False)
    monkeypatch.delenv("PENGUARD_AI_API_KEY", raising=False)
    monkeypatch.delenv("PENGUARD_ENABLE_LAB_DEMO_TOOLS", raising=False)
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    with pytest.raises(AIConfigurationError, match="AI provider is not configured"):
        get_ai_provider()


def test_scripted_ai_provider_requires_lab_demo_tools(monkeypatch):
    monkeypatch.setenv("PENGUARD_AI_PROVIDER", "scripted")
    monkeypatch.delenv("PENGUARD_ENABLE_LAB_DEMO_TOOLS", raising=False)
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    with pytest.raises(AIConfigurationError, match="scripted"):
        get_ai_provider()


def test_scripted_ai_provider_is_available_in_lab_mode(monkeypatch):
    monkeypatch.setenv("PENGUARD_AI_PROVIDER", "scripted")
    monkeypatch.setenv("PENGUARD_ENABLE_LAB_DEMO_TOOLS", "true")
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    provider = get_ai_provider()

    assert provider.name == "scripted"


def test_real_ai_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("PENGUARD_AI_PROVIDER", "anthropic")
    monkeypatch.delenv("PENGUARD_AI_API_KEY", raising=False)
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    with pytest.raises(AIConfigurationError, match="PENGUARD_AI_API_KEY"):
        get_ai_provider()
