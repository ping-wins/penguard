"""Enterprise SOC Assistant settings.

The streaming SOC Assistant uses one active provider/model/API key for the
deployment. API keys are encrypted at rest and never returned by API responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.db.models import AiAgentSettingsModel

logger = logging.getLogger(__name__)

SETTINGS_ID = "default"
SUPPORTED_PROVIDERS = {"anthropic", "openai"}


def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_provider(provider: str) -> str:
    normalized = provider.lower().strip().replace("-", "_")
    if normalized in {"openai", "openai_compat", "openai_compatible"}:
        return "openai"
    if normalized == "anthropic":
        return "anthropic"
    return normalized


@dataclass(frozen=True)
class AiAgentSettings:
    provider: str = ""
    model: str = ""
    api_key: str = ""
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_error: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None

    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    @property
    def configured(self) -> bool:
        return (
            normalize_provider(self.provider) in SUPPORTED_PROVIDERS
            and bool(self.model)
            and bool(self.api_key)
        )

    def to_dict(self, *, redact: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "apiKeySet": self.api_key_set,
            "configured": self.configured,
            "lastTestedAt": _format_dt(self.last_tested_at),
            "lastTestStatus": self.last_test_status,
            "lastTestError": self.last_test_error,
            "updatedBy": self.updated_by,
            "updatedAt": _format_dt(self.updated_at),
        }
        if not redact:
            payload["apiKey"] = self.api_key
        return payload


class AiAgentSettingsStore(Protocol):
    def get(self) -> AiAgentSettings | None: ...

    def upsert(self, **fields: Any) -> AiAgentSettings: ...


class InMemoryAiAgentSettingsStore:
    def __init__(self) -> None:
        self._row: AiAgentSettings | None = None

    def get(self) -> AiAgentSettings | None:
        return self._row

    def upsert(self, **fields: Any) -> AiAgentSettings:
        existing = self._row or AiAgentSettings()
        api_key = fields.get("api_key", existing.api_key)
        row = AiAgentSettings(
            provider=fields.get("provider", existing.provider),
            model=fields.get("model", existing.model),
            api_key=api_key or "",
            last_tested_at=fields.get("last_tested_at", existing.last_tested_at),
            last_test_status=fields.get(
                "last_test_status",
                existing.last_test_status,
            ),
            last_test_error=fields.get("last_test_error", existing.last_test_error),
            updated_by=fields.get("updated_by", existing.updated_by),
            updated_at=datetime.now(UTC),
        )
        self._row = row
        return row


class SqlAlchemyAiAgentSettingsStore:
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
            return
        if engine is None:
            if database_url is None:
                raise ValueError("database_url, engine, or session_factory required")
            engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def get(self) -> AiAgentSettings | None:
        with self._session_factory() as db:
            row = db.get(AiAgentSettingsModel, SETTINGS_ID)
            if row is None:
                return None
            return self._from_model(row)

    def upsert(self, **fields: Any) -> AiAgentSettings:
        with self._session_factory() as db:
            row = db.get(AiAgentSettingsModel, SETTINGS_ID)
            if row is None:
                row = AiAgentSettingsModel(id=SETTINGS_ID)
                db.add(row)
            if "provider" in fields:
                row.provider = fields["provider"]
            if "model" in fields:
                row.model = fields["model"]
            if "api_key" in fields:
                api_key = fields["api_key"]
                row.api_key_blob = self._encrypt(api_key) if api_key else None
            if "last_tested_at" in fields:
                row.last_tested_at = fields["last_tested_at"]
            if "last_test_status" in fields:
                row.last_test_status = fields["last_test_status"]
            if "last_test_error" in fields:
                row.last_test_error = fields["last_test_error"]
            if "updated_by" in fields:
                row.updated_by = fields["updated_by"]
            row.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(row)
            return self._from_model(row)

    def _from_model(self, row: AiAgentSettingsModel) -> AiAgentSettings:
        return AiAgentSettings(
            provider=row.provider or "",
            model=row.model or "",
            api_key=self._decrypt(row.api_key_blob),
            last_tested_at=row.last_tested_at,
            last_test_status=row.last_test_status,
            last_test_error=row.last_test_error,
            updated_by=row.updated_by,
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
            logger.warning("ai_agent_settings_decrypt_failed")
            return ""


@lru_cache
def get_ai_agent_settings_store() -> AiAgentSettingsStore:
    settings = get_settings()
    if settings.mock_mode:
        return InMemoryAiAgentSettingsStore()
    secret = settings.token_encryption_key or settings.secret_key or "ai-agent-settings-fallback"
    return SqlAlchemyAiAgentSettingsStore(
        cipher=TokenCipher.from_secret(secret),
        database_url=settings.database_url,
    )
