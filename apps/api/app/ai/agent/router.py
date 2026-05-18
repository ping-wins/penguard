"""Backend routing for the streaming agent runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.agent.backends.base import AgentBackend
from app.ai.agent.roles import RoleConfig
from app.ai.agent.settings import get_ai_agent_settings_store, normalize_provider


class AgentNotConfiguredError(RuntimeError):
    """Raised when the deployment has no usable enterprise assistant settings."""


@dataclass(frozen=True)
class AgentCredential:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None


def pick_backend(role: RoleConfig, user_id: str | None) -> AgentBackend:
    del role, user_id
    credential = _resolve_credentials()

    provider = _normalize_provider(credential.provider)

    if provider == "anthropic":
        from app.ai.agent.backends.anthropic import AnthropicBackend

        return AnthropicBackend(
            api_key=credential.api_key,
            model=credential.model,
            base_url=credential.base_url or "https://api.anthropic.com",
        )
    if provider == "openai":
        from app.ai.agent.backends.openai import OpenAIBackend

        return OpenAIBackend(
            api_key=credential.api_key,
            model=credential.model,
            base_url=credential.base_url or "https://api.openai.com/v1",
        )
    if provider == "gemini":
        from app.ai.agent.backends.gemini import GeminiBackend

        return GeminiBackend(
            api_key=credential.api_key,
            model=credential.model,
            base_url=credential.base_url or "https://generativelanguage.googleapis.com",
        )
    raise AgentNotConfiguredError("SOC Assistant provider is not configured")


def _resolve_credentials() -> AgentCredential:
    settings = get_ai_agent_settings_store().get()
    if settings is None or not settings.configured:
        raise AgentNotConfiguredError("SOC Assistant provider is not configured")
    return AgentCredential(
        provider=normalize_provider(settings.provider),
        model=settings.model,
        api_key=settings.api_key,
        base_url=getattr(settings, "base_url", None),
    )


def _normalize_provider(provider: str) -> str:
    return normalize_provider(provider)
