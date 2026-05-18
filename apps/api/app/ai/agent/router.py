"""Backend routing for the streaming agent runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.ai.agent.backends.base import AgentBackend
from app.ai.agent.backends.scripted import ScriptedBackend
from app.ai.agent.roles import AgentRoleTier, RoleConfig
from app.ai.preferences import get_preference_store
from app.core.config import get_settings

ANTHROPIC_MODELS: dict[AgentRoleTier, str] = {
    "fast": "claude-haiku-4-5-20251001",
    "balanced": "claude-sonnet-4-6",
    "deep": "claude-opus-4-7",
}
OPENAI_MODELS: dict[AgentRoleTier, str] = {
    "fast": "gpt-4o-mini",
    "balanced": "gpt-4o",
    "deep": "gpt-4o",
}


@dataclass(frozen=True)
class AgentCredential:
    provider: str
    api_key: str
    base_url: str = ""


def pick_backend(role: RoleConfig, user_id: str | None) -> AgentBackend:
    credential = _resolve_credentials(user_id)
    if credential is None:
        return ScriptedBackend()

    provider = _normalize_provider(credential.provider)
    tier = _resolve_role_tier(role)

    if provider == "anthropic":
        from app.ai.agent.backends.anthropic import AnthropicBackend

        return AnthropicBackend(
            api_key=credential.api_key,
            model=_resolve_model("anthropic", tier),
            base_url=credential.base_url or "https://api.anthropic.com",
        )
    if provider == "openai":
        from app.ai.agent.backends.openai import OpenAIBackend

        return OpenAIBackend(
            api_key=credential.api_key,
            model=_resolve_model("openai", tier),
            base_url=credential.base_url or "https://api.openai.com/v1",
        )
    return ScriptedBackend()


def _resolve_role_tier(role: RoleConfig) -> AgentRoleTier:
    env_name = f"FORTIDASHBOARD_ROLE_{role.id.upper().replace('-', '_')}_TIER"
    override = (os.getenv(env_name) or "").lower().strip()
    if override in {"fast", "balanced", "deep"}:
        return override  # type: ignore[return-value]
    return role.tier


def _resolve_model(provider: str, tier: AgentRoleTier) -> str:
    """Per-tier model override via env. Lets operators point the
    OpenAI-compatible backend at non-OpenAI endpoints (Gemini via
    `/v1beta/openai`, Ollama, etc.) without touching the tier table.

        FORTIDASHBOARD_OPENAI_MODEL_FAST=gemini-2.0-flash-lite
        FORTIDASHBOARD_OPENAI_MODEL_BALANCED=gemini-2.0-flash
        FORTIDASHBOARD_OPENAI_MODEL_DEEP=gemini-2.5-pro
        FORTIDASHBOARD_ANTHROPIC_MODEL_FAST=<id>
        FORTIDASHBOARD_ANTHROPIC_MODEL_BALANCED=<id>
        FORTIDASHBOARD_ANTHROPIC_MODEL_DEEP=<id>
    """
    env_name = f"FORTIDASHBOARD_{provider.upper()}_MODEL_{tier.upper()}"
    override = (os.getenv(env_name) or "").strip()
    if override:
        return override
    table = ANTHROPIC_MODELS if provider == "anthropic" else OPENAI_MODELS
    return table[tier]


def _resolve_credentials(user_id: str | None) -> AgentCredential | None:
    if user_id:
        try:
            pref = get_preference_store().get(user_id)
        except Exception:
            pref = None
        if pref is not None and pref.mode == "api":
            provider = _normalize_provider(pref.provider)
            api_key = _key_for_preference(pref, provider)
            if provider in {"anthropic", "openai"} and api_key:
                return AgentCredential(provider=provider, api_key=api_key)

    settings = get_settings()
    provider = _normalize_provider(getattr(settings, "ai_provider", "") or "")
    api_key = getattr(settings, "ai_api_key", "") or ""
    if provider in {"anthropic", "openai"} and api_key:
        return AgentCredential(
            provider=provider,
            api_key=api_key,
            base_url=getattr(settings, "ai_base_url", "") or "",
        )
    return None


def _key_for_preference(pref: object, provider: str) -> str:
    api_keys = getattr(pref, "api_keys", None)
    if isinstance(api_keys, dict):
        value = api_keys.get(provider) or api_keys.get(getattr(pref, "provider", ""))
        if value:
            return str(value)
    return str(getattr(pref, "api_key", "") or "")


def _normalize_provider(provider: str) -> str:
    normalized = provider.lower().strip().replace("-", "_")
    if normalized in {"openai", "openai_compat", "openai_compatible"}:
        return "openai"
    if normalized == "anthropic":
        return "anthropic"
    return normalized
