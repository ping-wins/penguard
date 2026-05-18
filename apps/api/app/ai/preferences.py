"""Per-user AI preferences — provider, model, API key.

Reads/writes `user_ai_preferences` rows. API keys are encrypted with the
shared `TokenCipher` so a database dump never reveals the user's key.

`build_provider_for_user(user_id)` returns a configured AIProvider for the
given user, or `None` if the user hasn't saved a preference yet — callers
fall back to `get_ai_provider()` (env-driven) in that case.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.cli_provider import CliAIProvider
from app.ai.provider import (
    AIConfigurationError,
    AIProvider,
    AnthropicAIProvider,
    GeminiAIProvider,
    OpenAICompatibleAIProvider,
    ScriptedAIProvider,
)
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.db.models import UserAiPreferenceModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserAiPreference:
    user_id: str
    mode: str = "api"  # api | cli
    provider: str = "gemini"
    model: str = ""
    api_key: str = ""
    api_keys: dict[str, str] = field(default_factory=dict)
    cli_binary: str = ""
    updated_at: datetime | None = None

    def to_dict(self, *, redact: bool = True) -> dict[str, Any]:
        api_keys_set = sorted(provider for provider, key in self.api_keys.items() if key)
        return {
            "userId": self.user_id,
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "apiKeySet": bool(self.api_key) or bool(api_keys_set),
            "apiKeysSet": api_keys_set,
            "apiKey": "" if redact else self.api_key,
            "cliBinary": self.cli_binary,
            "updatedAt": (
                self.updated_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                if self.updated_at
                else None
            ),
        }


class PreferenceStore(Protocol):
    def get(self, user_id: str) -> UserAiPreference | None: ...

    def upsert(self, *, user_id: str, **fields: Any) -> UserAiPreference: ...


class InMemoryPreferenceStore:
    def __init__(self) -> None:
        self._rows: dict[str, UserAiPreference] = {}

    def get(self, user_id: str) -> UserAiPreference | None:
        return self._rows.get(user_id)

    def upsert(self, *, user_id: str, **fields: Any) -> UserAiPreference:
        existing = self._rows.get(user_id)
        next_row = UserAiPreference(
            user_id=user_id,
            mode=fields.get("mode", existing.mode if existing else "api"),
            provider=fields.get(
                "provider", existing.provider if existing else "gemini"
            ),
            model=fields.get("model", existing.model if existing else ""),
            api_key=fields.get("api_key", existing.api_key if existing else ""),
            api_keys=fields.get("api_keys", existing.api_keys if existing else {}),
            cli_binary=fields.get(
                "cli_binary", existing.cli_binary if existing else ""
            ),
            updated_at=datetime.now(UTC),
        )
        self._rows[user_id] = next_row
        return next_row


class SqlAlchemyPreferenceStore:
    def __init__(
        self,
        *,
        cipher: TokenCipher,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
    ) -> None:
        self._cipher = cipher
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self._session_factory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )

    def get(self, user_id: str) -> UserAiPreference | None:
        with self._session_factory() as db:
            row = db.get(UserAiPreferenceModel, user_id)
            if row is None:
                return None
            api_key = self._decrypt(row.api_key_blob)
            api_keys = self._decrypt_key_map(row.api_keys_blob)
            return UserAiPreference(
                user_id=row.user_id,
                mode=row.mode,
                provider=row.provider,
                model=row.model,
                api_key=api_key,
                api_keys=api_keys,
                cli_binary=row.cli_binary or "",
                updated_at=row.updated_at,
            )

    def upsert(self, *, user_id: str, **fields: Any) -> UserAiPreference:
        api_key = fields.get("api_key")
        api_key_blob = self._encrypt(api_key) if api_key else None
        api_keys = fields.get("api_keys")
        with self._session_factory() as db:
            row = db.get(UserAiPreferenceModel, user_id)
            if row is None:
                row = UserAiPreferenceModel(user_id=user_id)
                db.add(row)
            if "mode" in fields:
                row.mode = fields["mode"]
            if "provider" in fields:
                row.provider = fields["provider"]
            if "model" in fields:
                row.model = fields["model"]
            if "cli_binary" in fields:
                row.cli_binary = fields["cli_binary"] or None
            # api_key: explicit "" clears, omit leaves existing untouched.
            if "api_key" in fields:
                if api_key:
                    row.api_key_blob = api_key_blob
                elif api_key == "":
                    row.api_key_blob = None
            if "api_keys" in fields:
                row.api_keys_blob = self._encrypt_key_map(api_keys)
            row.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(row)
            decrypted_key = self._decrypt(row.api_key_blob)
            decrypted_keys = self._decrypt_key_map(row.api_keys_blob)
            return UserAiPreference(
                user_id=row.user_id,
                mode=row.mode,
                provider=row.provider,
                model=row.model,
                api_key=decrypted_key,
                api_keys=decrypted_keys,
                cli_binary=row.cli_binary or "",
                updated_at=row.updated_at,
            )

    def _encrypt(self, plain: str) -> str:
        return self._cipher.encrypt({"k": plain})

    def _decrypt(self, blob: str | None) -> str:
        if not blob:
            return ""
        try:
            return str(self._cipher.decrypt(blob).get("k") or "")
        except Exception:  # noqa: BLE001
            logger.warning("user_ai_preference_decrypt_failed")
            return ""

    def _encrypt_key_map(self, values: Any) -> dict[str, str] | None:
        if not isinstance(values, dict):
            return None
        encrypted: dict[str, str] = {}
        for provider, key in values.items():
            provider_name = str(provider).lower().strip()
            if not provider_name:
                continue
            if key:
                encrypted[provider_name] = self._encrypt(str(key))
        return encrypted or None

    def _decrypt_key_map(self, blob: Any) -> dict[str, str]:
        if not isinstance(blob, dict):
            return {}
        decrypted: dict[str, str] = {}
        for provider, encrypted in blob.items():
            plain = self._decrypt(str(encrypted) if encrypted else None)
            if plain:
                decrypted[str(provider)] = plain
        return decrypted


@lru_cache
def get_preference_store() -> PreferenceStore:
    settings = get_settings()
    if settings.mock_mode:
        return InMemoryPreferenceStore()
    secret = (
        settings.token_encryption_key
        or settings.secret_key
        or "user-ai-pref-fallback"
    )
    return SqlAlchemyPreferenceStore(
        cipher=TokenCipher.from_secret(secret),
        database_url=settings.database_url,
    )


def build_provider_for_user(user_id: str) -> AIProvider | None:
    """Construct an AIProvider from the user's saved preference, or None."""
    store = get_preference_store()
    pref = store.get(user_id)
    if pref is None:
        return None
    if pref.mode == "cli":
        if not pref.cli_binary:
            return None
        try:
            return CliAIProvider(
                binary_path=pref.cli_binary,
                model=pref.model or "",
            )
        except AIConfigurationError as exc:
            logger.warning("cli_provider_init_failed user=%s err=%s", user_id, exc)
            return None
    if pref.mode != "api":
        return None
    if not pref.api_key:
        api_keys = pref.api_keys or {}
        pref_key = api_keys.get(pref.provider.lower().strip())
        if not pref_key:
            return None
    else:
        pref_key = pref.api_key
    provider = pref.provider.lower().strip()
    model = pref.model or _default_model_for(provider)
    if provider == "gemini":
        return GeminiAIProvider(api_key=pref_key, model=model)
    if provider == "anthropic":
        return AnthropicAIProvider(api_key=pref_key, model=model)
    if provider in {"openai", "openai_compat", "openai-compatible"}:
        return OpenAICompatibleAIProvider(api_key=pref_key, model=model)
    if provider == "scripted":
        return ScriptedAIProvider()
    raise AIConfigurationError(f"Unsupported user provider: {pref.provider}")


def _default_model_for(provider: str) -> str:
    return {
        "gemini": "gemini-flash-latest",
        "anthropic": "claude-haiku-4-5-20251001",
        "openai": "gpt-4o-mini",
        "openai_compat": "gpt-4o-mini",
        "openai-compatible": "gpt-4o-mini",
    }.get(provider, "")
