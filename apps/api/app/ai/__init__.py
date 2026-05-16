"""AI provider abstraction for the FortiDashboard cockpit assistant.

This package exposes a thin protocol (`AIProvider`) and a few built-in
adapters: an Anthropic adapter, an OpenAI-compatible adapter and a
deterministic "scripted" adapter used in tests and offline demos. Every
caller goes through `get_ai_provider()` so the rest of the codebase never has
to know which backend is configured.
"""

from app.ai.preferences import (
    UserAiPreference,
    build_provider_for_user,
    get_preference_store,
)
from app.ai.provider import (
    AIConfigurationError,
    AIProvider,
    ChatMessage,
    ContainmentStep,
    ContainmentSuggestion,
    IncidentAnalysis,
    IncidentContext,
    MitreTechnique,
    get_ai_provider,
)


def resolve_ai_provider(user_id: str | None = None) -> AIProvider:
    """Pick the user's saved provider, falling back to env-driven config."""
    if user_id:
        provider = build_provider_for_user(user_id)
        if provider is not None:
            return provider
    return get_ai_provider()


__all__ = [
    "AIConfigurationError",
    "AIProvider",
    "ChatMessage",
    "ContainmentStep",
    "ContainmentSuggestion",
    "IncidentAnalysis",
    "IncidentContext",
    "MitreTechnique",
    "UserAiPreference",
    "build_provider_for_user",
    "get_ai_provider",
    "get_preference_store",
    "resolve_ai_provider",
]
