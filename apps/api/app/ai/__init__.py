"""AI provider abstraction for the FortiDashboard cockpit assistant.

This package exposes a thin protocol (`AIProvider`) and a few built-in
adapters: an Anthropic adapter, an OpenAI-compatible adapter and a
deterministic "scripted" adapter used in tests and offline demos. Every
caller goes through `get_ai_provider()` so the rest of the codebase never has
to know which backend is configured.
"""

from app.ai.provider import (
    AIProvider,
    ChatMessage,
    ContainmentStep,
    ContainmentSuggestion,
    IncidentAnalysis,
    IncidentContext,
    MitreTechnique,
    get_ai_provider,
)

__all__ = [
    "AIProvider",
    "ChatMessage",
    "ContainmentStep",
    "ContainmentSuggestion",
    "IncidentAnalysis",
    "IncidentContext",
    "MitreTechnique",
    "get_ai_provider",
]
