# Unified SOC Assistant Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible multi-agent/backend UX with one SOC Assistant configured by an enterprise provider/model/API key and governed by RBAC.

**Architecture:** Add an enterprise AI agent settings store and admin-only API, then route `/api/ai/agent/*` through that singleton configuration instead of per-user preferences or frontend-selected backends. The frontend removes agent role/backend/CLI controls and exposes a single SOC Assistant panel plus admin-only settings.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, Vue 3, Pinia, vue-i18n, Vitest, Tailwind CSS, Lucide Vue.

---

## Scope

This plan implements Phase 1 from [`2026-05-18-unified-soc-assistant-ux-design.md`](../specs/2026-05-18-unified-soc-assistant-ux-design.md).

Included:

- New permissions `ai.agent.manage` and `playbooks.manage`.
- Enterprise SOC Assistant provider/model/API key settings.
- Admin/permission-gated settings API.
- Streaming agent sessions that no longer accept user-facing `role` or `backend`.
- No silent scripted fallback when the enterprise provider is missing.
- Frontend SOC Assistant UX without backend/role selectors.
- Settings UI without Claude/Codex CLI mode.
- i18n for new user-facing strings.

Not included in this plan:

- Permission-derived tool filtering for every dashboard tool.
- Dashboard management tools beyond the current registered tools.
- Agentic playbook graph drafting/apply tools.
- Legacy `/api/ai/chat` removal.
- Database deletion of `user_ai_preferences`.

Those are separate implementation plans after this first cut is stable.

## File Structure

Backend files:

- Modify `apps/api/app/auth/permissions.py`: add permission slugs.
- Modify `apps/api/app/db/models.py`: add `AiAgentSettingsModel`.
- Create `apps/api/migrations/versions/20260518_0020_create_ai_agent_settings.py`: create singleton settings table.
- Create `apps/api/app/ai/agent/settings.py`: settings dataclass, in-memory store, SQLAlchemy store, encryption, provider test helper.
- Modify `apps/api/app/ai/agent/router.py`: route backend selection through enterprise settings and raise a typed not-configured error.
- Modify `apps/api/app/routers/ai_agent.py`: remove frontend-selected role/backend contract, expose settings endpoints or delegate to a settings router, and return not-configured errors clearly.
- Modify `apps/api/app/main.py`: include any new router if settings endpoints are split out.
- Modify `apps/api/tests/test_ai_agent.py`: update session/backends expectations.
- Create `apps/api/tests/test_ai_agent_settings.py`: settings persistence, permissions, redaction, and provider routing tests.
- Modify `apps/api/tests/test_roles_rbac.py`: permission catalog assertions for new slugs.

Frontend files:

- Modify `apps/web/src/services/aiAgentClient.ts`: remove backend/role UX APIs from session creation path; add optional settings client only if not split.
- Create `apps/web/src/services/socAssistantSettingsClient.ts`: enterprise settings API client.
- Modify `apps/web/src/stores/useAiAgentStore.ts`: no role/backend catalog dependency; aggregate text deltas.
- Create `apps/web/src/stores/useSocAssistantSettingsStore.ts`: admin settings store.
- Modify `apps/web/src/components/ai/AgentPanel.vue`: one SOC Assistant, no role/backend selectors, configured/unconfigured states.
- Replace or heavily modify `apps/web/src/components/settings/AiPreferencesPanel.vue`: enterprise SOC Assistant settings panel with no CLI local mode.
- Modify `apps/web/src/components/settings/SettingsModal.vue`: show AI settings only for `ai.agent.manage` or admin.
- Modify `apps/web/src/i18n/messages/pt-BR.ts` and `apps/web/src/i18n/messages/en-US.ts`: SOC Assistant and permission labels.
- Modify `apps/web/tests/unit/aiAgentStore.test.ts`: no backend/role selection; text delta aggregation.
- Replace or modify `apps/web/tests/unit/aiPreferencesClient.test.ts`: enterprise settings client tests.

---

### Task 1: Add SOC Assistant Permissions

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_roles_rbac.py`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`

- [ ] **Step 1: Write failing backend permission catalog test**

Add this test to `apps/api/tests/test_roles_rbac.py` near the existing permission catalog tests:

```python
def test_permission_catalog_includes_soc_assistant_management(make_client, db_session):
    client = make_client(user_id="admin-user", roles=["admin"])

    response = client.get("/api/roles/permissions/catalog")

    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()}
    assert "ai.agent.manage" in slugs
    assert "playbooks.manage" in slugs
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
cd apps/api && uv run pytest tests/test_roles_rbac.py::test_permission_catalog_includes_soc_assistant_management -q
```

Expected: FAIL because `ai.agent.manage` and `playbooks.manage` are not in `PERMISSION_CATALOG`.

- [ ] **Step 3: Add permission definitions**

In `apps/api/app/auth/permissions.py`, add these entries to `PERMISSION_CATALOG`:

```python
    PermissionDef(
        slug="playbooks.manage",
        category="playbooks",
        label_key="settings.roles.permission.playbooks.manage.label",
        description_key="settings.roles.permission.playbooks.manage.description",
    ),
    PermissionDef(
        slug="ai.agent.manage",
        category="ai",
        label_key="settings.roles.permission.ai.agent.manage.label",
        description_key="settings.roles.permission.ai.agent.manage.description",
    ),
```

Place `playbooks.manage` next to `playbooks.execute` and `ai.agent.manage` next to `ai.agent.approve`.

- [ ] **Step 4: Add i18n labels**

In `apps/web/src/i18n/messages/pt-BR.ts`, inside `settings.roles.permission`, add:

```ts
        'playbooks.manage': {
          label: 'Gerenciar playbooks',
          description: 'Criar, editar e validar definições de playbooks SOAR.',
        },
        'ai.agent.manage': {
          label: 'Configurar Assistente SOC',
          description: 'Configurar provider, modelo e chave de API do Assistente SOC da empresa.',
        },
```

In `apps/web/src/i18n/messages/en-US.ts`, inside `settings.roles.permission`, add:

```ts
        'playbooks.manage': {
          label: 'Manage playbooks',
          description: 'Create, edit and validate SOAR playbook definitions.',
        },
        'ai.agent.manage': {
          label: 'Configure SOC Assistant',
          description: 'Configure the enterprise SOC Assistant provider, model and API key.',
        },
```

- [ ] **Step 5: Verify permission catalog test passes**

Run:

```bash
cd apps/api && uv run pytest tests/test_roles_rbac.py::test_permission_catalog_includes_soc_assistant_management -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/auth/permissions.py apps/api/tests/test_roles_rbac.py apps/web/src/i18n/messages/pt-BR.ts apps/web/src/i18n/messages/en-US.ts
git commit -m "feat(auth): add SOC assistant permissions"
```

---

### Task 2: Add Enterprise AI Agent Settings Store

**Files:**
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/migrations/versions/20260518_0020_create_ai_agent_settings.py`
- Create: `apps/api/app/ai/agent/settings.py`
- Create: `apps/api/tests/test_ai_agent_settings.py`

- [ ] **Step 1: Write failing store tests**

Create `apps/api/tests/test_ai_agent_settings.py` with:

```python
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
```

- [ ] **Step 2: Run store tests to verify they fail**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py -q
```

Expected: FAIL with import error for `app.ai.agent.settings`.

- [ ] **Step 3: Add database model**

In `apps/api/app/db/models.py`, after `UserAiPreferenceModel`, add:

```python
class AiAgentSettingsModel(Base):
    __tablename__ = "ai_agent_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    api_key_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
```

- [ ] **Step 4: Add Alembic migration**

Create `apps/api/migrations/versions/20260518_0020_create_ai_agent_settings.py`:

```python
"""create enterprise AI agent settings

Revision ID: 20260518_0020
Revises: 20260518_0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0020"
down_revision: str | None = "20260518_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_settings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("api_key_blob", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_error", sa.String(length=512), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_agent_settings")
```

- [ ] **Step 5: Implement settings store**

Create `apps/api/app/ai/agent/settings.py`:

```python
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
        return normalize_provider(self.provider) in SUPPORTED_PROVIDERS and bool(self.model) and bool(self.api_key)

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
            last_test_status=fields.get("last_test_status", existing.last_test_status),
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
```

- [ ] **Step 6: Run store tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py -q
```

Expected: PASS.

- [ ] **Step 7: Run migration syntax check**

Run:

```bash
cd apps/api && uv run alembic upgrade head
```

Expected: PASS against the configured local test/dev database. If the environment lacks a database, record the connection error in the task handoff and still run `uv run pytest tests/test_ai_agent_settings.py -q`.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/db/models.py apps/api/migrations/versions/20260518_0020_create_ai_agent_settings.py apps/api/app/ai/agent/settings.py apps/api/tests/test_ai_agent_settings.py
git commit -m "feat(ai): add enterprise assistant settings store"
```

---

### Task 3: Add SOC Assistant Settings API

**Files:**
- Modify: `apps/api/app/routers/ai_agent.py`
- Modify: `apps/api/tests/test_ai_agent_settings.py`

- [ ] **Step 1: Add failing API tests**

Append these tests to `apps/api/tests/test_ai_agent_settings.py`:

```python
from fastapi.testclient import TestClient

from app.ai.agent.settings import get_ai_agent_settings_store
from app.main import app


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    get_ai_agent_settings_store.cache_clear()


def test_get_ai_agent_settings_requires_permission():
    client = TestClient(app)

    response = client.get("/api/ai/agent/settings")

    assert response.status_code == 403


def test_admin_can_save_and_read_ai_agent_settings_redacted():
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


def test_update_ai_agent_settings_accepts_gemini_provider():
    client = TestClient(app)

    response = client.put(
        "/api/ai/agent/settings",
        headers=csrf_headers(client),
        json={"provider": "gemini", "model": "gemini-flash-latest", "apiKey": "k"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "gemini"


def test_test_ai_agent_settings_marks_missing_config_failure():
    client = TestClient(app)

    response = client.post("/api/ai/agent/settings/test", headers=csrf_headers(client))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "not_configured"
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py -q
```

Expected: FAIL because `/api/ai/agent/settings` endpoints do not exist.

- [ ] **Step 3: Add request/response models to `ai_agent.py`**

In `apps/api/app/routers/ai_agent.py`, import settings helpers:

```python
from app.ai.agent.settings import (
    SUPPORTED_PROVIDERS,
    get_ai_agent_settings_store,
    normalize_provider,
)
```

Add Pydantic models near existing request models:

```python
class AiAgentSettingsUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, alias="apiKey", max_length=1024)


class AiAgentSettingsTestResponse(BaseModel):
    ok: bool
    status: str
    error: str | None = None
```

- [ ] **Step 4: Add settings endpoints**

In `apps/api/app/routers/ai_agent.py`, add:

```python
@router.get("/settings")
def get_ai_agent_settings(
    _admin: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
) -> dict[str, Any]:
    settings = get_ai_agent_settings_store().get()
    if settings is None:
        return {
            "provider": "",
            "model": "",
            "apiKeySet": False,
            "configured": False,
            "lastTestedAt": None,
            "lastTestStatus": None,
            "lastTestError": None,
            "updatedBy": None,
            "updatedAt": None,
        }
    return settings.to_dict(redact=True)


@router.put("/settings")
def update_ai_agent_settings(
    request: Request,
    payload: Annotated[AiAgentSettingsUpdate, Body(...)],
    current_user: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if payload.provider is not None:
        provider = normalize_provider(payload.provider)
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"provider '{payload.provider}' not supported")
        fields["provider"] = provider
    if payload.model is not None:
        fields["model"] = payload.model.strip()
    if payload.api_key is not None:
        fields["api_key"] = payload.api_key
    fields["updated_by"] = current_user.get("email") or str(current_user.get("id") or "")
    settings = get_ai_agent_settings_store().upsert(**fields)
    audit_store.record(
        action="ai.agent.settings.updated",
        outcome="success",
        email=current_user.get("email"),
        user_id=current_user.get("id"),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "provider": settings.provider,
            "model": settings.model,
            "apiKeySet": settings.api_key_set,
        },
    )
    return settings.to_dict(redact=True)


@router.post("/settings/test", response_model=AiAgentSettingsTestResponse)
def test_ai_agent_settings(
    current_user: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> AiAgentSettingsTestResponse:
    store = get_ai_agent_settings_store()
    settings = store.get()
    if settings is None or not settings.configured:
        store.upsert(
            last_tested_at=datetime.now(UTC),
            last_test_status="not_configured",
            last_test_error="SOC Assistant provider is not configured",
            updated_by=current_user.get("email") or str(current_user.get("id") or ""),
        )
        return AiAgentSettingsTestResponse(
            ok=False,
            status="not_configured",
            error="SOC Assistant provider is not configured",
        )
    store.upsert(
        last_tested_at=datetime.now(UTC),
        last_test_status="success",
        last_test_error=None,
        updated_by=current_user.get("email") or str(current_user.get("id") or ""),
    )
    return AiAgentSettingsTestResponse(ok=True, status="success", error=None)
```

Also add:

```python
from datetime import UTC, datetime
```

at the top of `apps/api/app/routers/ai_agent.py`.

- [ ] **Step 5: Run settings API tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py -q
```

Expected: PASS.

- [ ] **Step 6: Run focused router smoke**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent.py::test_list_tools_endpoint_returns_input_schemas tests/test_ai_agent_settings.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routers/ai_agent.py apps/api/tests/test_ai_agent_settings.py
git commit -m "feat(ai): add enterprise assistant settings API"
```

---

### Task 4: Route Agent Sessions Through Enterprise Settings

**Files:**
- Modify: `apps/api/app/ai/agent/router.py`
- Modify: `apps/api/app/routers/ai_agent.py`
- Modify: `apps/api/tests/test_ai_agent.py`
- Modify: `apps/api/tests/test_ai_agent_settings.py`

- [ ] **Step 1: Add failing routing tests**

In `apps/api/tests/test_ai_agent_settings.py`, add:

```python
from app.ai.agent.roles import get_role
from app.ai.agent.router import AgentNotConfiguredError, pick_backend
from app.ai.agent.settings import InMemoryAiAgentSettingsStore


def test_agent_router_uses_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    store.upsert(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test",
        updated_by="admin@example.com",
    )
    monkeypatch.setattr("app.ai.agent.router.get_ai_agent_settings_store", lambda: store)

    backend = pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]

    assert backend.name == "openai"
    assert backend.model == "gpt-4o"


def test_agent_router_raises_without_enterprise_settings(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    monkeypatch.setattr("app.ai.agent.router.get_ai_agent_settings_store", lambda: store)

    with pytest.raises(AgentNotConfiguredError):
        pick_backend(get_role("chat"), "user-1")  # type: ignore[arg-type]
```

Add `import pytest` to the file.

- [ ] **Step 2: Update HTTP session tests for no role/backend request**

In `apps/api/tests/test_ai_agent.py`, change `test_create_session_returns_session_id` to configure the enterprise settings store and post only locale:

```python
def test_create_session_returns_session_id(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    store.upsert(provider="anthropic", model="claude-sonnet-4-6", api_key="sk-test", updated_by="admin")
    monkeypatch.setattr("app.ai.agent.router.get_ai_agent_settings_store", lambda: store)

    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"locale": "pt-BR"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["backend"] == "anthropic"
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["role"] == "soc-assistant"
    assert payload["tokensIn"] == 0
    assert payload["tokensOut"] == 0
    assert payload["sessionId"]
```

Replace `test_create_session_rejects_unknown_backend` with:

```python
def test_create_session_rejects_frontend_backend_selection():
    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"backend": "scripted"},
    )
    assert response.status_code == 422
```

Add import:

```python
from app.ai.agent.settings import InMemoryAiAgentSettingsStore
```

- [ ] **Step 3: Run routing tests to verify they fail**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py::test_agent_router_uses_enterprise_settings tests/test_ai_agent_settings.py::test_agent_router_raises_without_enterprise_settings tests/test_ai_agent.py::test_create_session_returns_session_id tests/test_ai_agent.py::test_create_session_rejects_frontend_backend_selection -q
```

Expected: FAIL because routing still uses user preferences and `CreateSessionRequest` still accepts `backend`.

- [ ] **Step 4: Change backend routing to enterprise settings**

In `apps/api/app/ai/agent/router.py`, replace the per-user preference import:

```python
from app.ai.preferences import get_preference_store
```

with:

```python
from app.ai.agent.settings import get_ai_agent_settings_store, normalize_provider
```

Add:

```python
class AgentNotConfiguredError(RuntimeError):
    """Raised when the enterprise SOC Assistant provider is not configured."""
```

Change `pick_backend()` to:

```python
def pick_backend(role: RoleConfig, user_id: str | None) -> AgentBackend:
    credential = _resolve_credentials()
    if credential is None:
        raise AgentNotConfiguredError("SOC Assistant provider is not configured")

    provider = normalize_provider(credential.provider)
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
    raise AgentNotConfiguredError(f"SOC Assistant provider '{credential.provider}' is not supported")
```

Update `AgentCredential`:

```python
@dataclass(frozen=True)
class AgentCredential:
    provider: str
    model: str
    api_key: str
    base_url: str = ""
```

Replace `_resolve_credentials(user_id)` with:

```python
def _resolve_credentials() -> AgentCredential | None:
    settings = get_ai_agent_settings_store().get()
    if settings is None or not settings.configured:
        return None
    return AgentCredential(
        provider=settings.provider,
        model=settings.model,
        api_key=settings.api_key,
    )
```

Keep the tier model maps temporarily if other tests import them, but do not use them in `pick_backend()`.

- [ ] **Step 5: Update session request contract**

In `apps/api/app/routers/ai_agent.py`, change `CreateSessionRequest` to forbid extra fields and remove `role`, `backend`, and `model`:

```python
class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="pt-BR", min_length=2, max_length=16)
```

In `create_session()`, replace role/backend resolution with:

```python
    role = get_role("chat")
    if role is None:
        raise HTTPException(status_code=500, detail="agent role registry unavailable")
    try:
        backend = pick_backend(role, str(current_user["id"]))
    except AgentNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
```

Set stored role to `"soc-assistant"` while still using the internal chat prompt for now:

```python
        role_id="soc-assistant",
```

In `AgentRunner._run_locked_turn()`, resolve `soc-assistant` to internal `chat`:

```python
        role = get_role(session.role_id)
        if role is None and session.role_id == "soc-assistant":
            role = get_role("chat")
```

Import `AgentNotConfiguredError` in `apps/api/app/routers/ai_agent.py`:

```python
from app.ai.agent.router import AgentNotConfiguredError, pick_backend
```

- [ ] **Step 6: Convert no-provider create session behavior**

Add this test to `apps/api/tests/test_ai_agent.py`:

```python
def test_create_session_returns_conflict_when_assistant_unconfigured(monkeypatch):
    store = InMemoryAiAgentSettingsStore()
    monkeypatch.setattr("app.ai.agent.router.get_ai_agent_settings_store", lambda: store)

    client = TestClient(app)
    response = client.post(
        "/api/ai/agent/sessions",
        headers=csrf_headers(client),
        json={"locale": "pt-BR"},
    )

    assert response.status_code == 409
    assert "not configured" in response.json()["detail"]
```

- [ ] **Step 7: Run focused routing and session tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent_settings.py tests/test_ai_agent.py::test_create_session_returns_session_id tests/test_ai_agent.py::test_create_session_rejects_frontend_backend_selection tests/test_ai_agent.py::test_create_session_returns_conflict_when_assistant_unconfigured -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/ai/agent/router.py apps/api/app/ai/agent/runner.py apps/api/app/routers/ai_agent.py apps/api/tests/test_ai_agent.py apps/api/tests/test_ai_agent_settings.py
git commit -m "feat(ai): route assistant through enterprise provider"
```

---

### Task 5: Simplify Agent Client And Store

**Files:**
- Modify: `apps/web/src/services/aiAgentClient.ts`
- Modify: `apps/web/src/stores/useAiAgentStore.ts`
- Modify: `apps/web/tests/unit/aiAgentStore.test.ts`

- [ ] **Step 1: Add failing store test for no backend/role payload**

In `apps/web/tests/unit/aiAgentStore.test.ts`, add:

```ts
  it('starts a SOC Assistant session without role or backend', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_42' }))
      .mockResolvedValueOnce(jsonResponse(
        { sessionId: 'sess_1', backend: 'anthropic', model: 'claude-sonnet-4-6', role: 'soc-assistant', locale: 'pt-BR', createdAt: 1, tokensIn: 0, tokensOut: 0 },
        { status: 201 },
      ))
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.startSession()

    const createCall = fetcher.mock.calls[1]
    expect(createCall[0]).toBe('/api/ai/agent/sessions')
    expect(JSON.parse(createCall[1].body)).toEqual({ locale: 'pt-BR' })
    expect(store.session?.role).toBe('soc-assistant')
  })
```

- [ ] **Step 2: Add failing text aggregation test**

In `apps/web/tests/unit/aiAgentStore.test.ts`, add:

```ts
  it('aggregates streamed text deltas into one assistant trace entry', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'anthropic', model: 'claude-sonnet-4-6', role: 'soc-assistant', locale: 'pt-BR', createdAt: 1, tokensIn: 0, tokensOut: 0 },
      { status: 201 },
    )
    const stream = sseResponse([
      sseEvent({ type: 'step', kind: 'text_delta', step: 1, text: 'Olá ' }),
      sseEvent({ type: 'step', kind: 'text_delta', step: 1, text: 'SOC' }),
      sseEvent({ type: 'step', kind: 'done', step: 1, reply: 'Olá SOC', used_tools: [], tokens_in: 10, tokens_out: 3 }),
    ])
    const fetcher = vi.fn()
      .mockResolvedValueOnce(csrf)
      .mockResolvedValueOnce(sessionPayload)
      .mockResolvedValueOnce(stream)
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.startSession()
    await store.sendMessage('oi')

    const textEntries = store.trace.filter((entry) => entry.kind === 'text')
    expect(textEntries).toHaveLength(1)
    expect((textEntries[0] as { text: string }).text).toBe('Olá SOC')
  })
```

- [ ] **Step 3: Run web store tests to verify they fail**

Run:

```bash
cd apps/web && pnpm test -- aiAgentStore
```

Expected: FAIL because `startSession()` still sends role/backend when provided by callers and text deltas create separate trace entries.

- [ ] **Step 4: Update `createAgentSession()` payload**

In `apps/web/src/services/aiAgentClient.ts`, change the function to:

```ts
export async function createAgentSession(
  options: { locale?: string } = {},
): Promise<AgentSessionResponse> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/sessions', {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      locale: options.locale ?? 'pt-BR',
    }),
  })
  return parseOrThrow<AgentSessionResponse>(response, 'Falha ao criar sessão do Assistente SOC')
}
```

Leave `listAgentRoles()` and `listBackends()` exported only if other code still imports them during this task; remove them in Task 6 if no imports remain.

- [ ] **Step 5: Update store session API**

In `apps/web/src/stores/useAiAgentStore.ts`, change `startSession()` signature to:

```ts
  async function startSession(options: { locale?: string } = {}) {
```

and call:

```ts
      session.value = await createAgentSession(options)
```

Change `sendMessage()` fallback to:

```ts
      await startSession()
```

Change `consumeEvent()` text delta branch to append to the most recent text entry when the step matches:

```ts
    if (event.kind === 'text_delta') {
      const last = trace.value[trace.value.length - 1]
      if (last?.kind === 'text' && last.step === event.step) {
        last.text += event.text
      } else {
        trace.value.push({ kind: 'text', step: event.step, text: event.text })
      }
      return
    }
```

- [ ] **Step 6: Remove catalog dependency from store initialization**

In `apps/web/src/stores/useAiAgentStore.ts`, keep `ensureCatalog()` for tools only:

```ts
  async function ensureCatalog() {
    if (tools.value.length > 0) return
    isLoading.value = true
    try {
      tools.value = await listAgentTools()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }
```

Keep `roles` and `backends` refs only if tests or components still access them during Task 5; remove visible usage in Task 6.

- [ ] **Step 7: Update tests that call `startSession()` with backend**

In `apps/web/tests/unit/aiAgentStore.test.ts`, replace calls like:

```ts
await store.startSession({ role: 'incident-triage', backend: 'scripted' })
```

with:

```ts
await store.startSession()
```

Update mocked session payloads to use:

```ts
role: 'soc-assistant'
```

- [ ] **Step 8: Run focused web tests**

Run:

```bash
cd apps/web && pnpm test -- aiAgentStore
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/web/src/services/aiAgentClient.ts apps/web/src/stores/useAiAgentStore.ts apps/web/tests/unit/aiAgentStore.test.ts
git commit -m "feat(web): simplify SOC assistant session store"
```

---

### Task 6: Replace Assistant Panel UX

**Files:**
- Modify: `apps/web/src/components/ai/AgentPanel.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`

- [ ] **Step 1: Remove role/backend state from component**

In `apps/web/src/components/ai/AgentPanel.vue`, remove:

```ts
const selectedBackend = ref('scripted')
const selectedRole = ref('chat')
```

Change `onMounted()` to:

```ts
onMounted(async () => {
  await store.ensureCatalog()
})
```

Change `start()` to:

```ts
async function start() {
  await store.startSession()
}
```

Remove `activeRole`, `roleLabel()`, and the token budget lookup from backend role metadata. Use a fixed model badge:

```ts
const modelBadge = computed(() => {
  const model = store.session?.model || t('aiAgent.noModel')
  return t('aiAgent.modelBadge', {
    model,
    used: formatTokens(store.tokensIn + store.tokensOut),
  })
})
```

- [ ] **Step 2: Replace header controls**

In the `<template>`, replace the header title:

```vue
<span class="font-semibold text-theme-text">{{ t('aiAgent.title') }}</span>
```

Keep the start/end buttons, but remove both `<select id="agent-role">` and `<select id="agent-backend">`.

- [ ] **Step 3: Replace empty/backend hint text**

In `AgentPanel.vue`, replace:

```vue
{{ t('aiAgent.empty') }}
<span class="font-mono">{{ t('aiAgent.backendHint', { backend: selectedBackend }) }}</span>.
```

with:

```vue
{{ t('aiAgent.empty') }}
```

- [ ] **Step 4: Add configured error hint copy**

Keep `store.error` rendering, but make the default server conflict actionable by adding i18n keys:

In `apps/web/src/i18n/messages/pt-BR.ts`, replace the `aiAgent` section values with these changed keys:

```ts
    title: 'Assistente SOC',
    start: 'Iniciar',
    end: 'Encerrar',
    send: 'Enviar',
    empty: 'Envie uma pergunta sobre incidentes, integrações, playbooks, endpoints ou o estado do cockpit.',
    streaming: 'Respondendo...',
    promptHint: 'Pergunte ao Assistente SOC',
    modelBadge: '{model} · {used} tokens',
    noModel: 'Modelo pendente',
```

In `apps/web/src/i18n/messages/en-US.ts`, use:

```ts
    title: 'SOC Assistant',
    start: 'Start',
    end: 'End',
    send: 'Send',
    empty: 'Ask about incidents, integrations, playbooks, endpoints, or cockpit state.',
    streaming: 'Responding...',
    promptHint: 'Ask the SOC Assistant',
    modelBadge: '{model} · {used} tokens',
    noModel: 'Model pending',
```

Remove `roleLabel`, `backendLabel`, `defaultSuffix`, `backendHint`, and `roles` keys if no code references them after this task.

- [ ] **Step 5: Run TypeScript check via build**

Run:

```bash
cd apps/web && pnpm build
```

Expected: PASS. If unrelated build failures exist, run `cd apps/web && pnpm test -- aiAgentStore` and record the build failure in the handoff.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/ai/AgentPanel.vue apps/web/src/i18n/messages/pt-BR.ts apps/web/src/i18n/messages/en-US.ts
git commit -m "feat(web): present one SOC assistant"
```

---

### Task 7: Replace Per-User AI Preferences With Enterprise Settings UI

**Files:**
- Create: `apps/web/src/services/socAssistantSettingsClient.ts`
- Create: `apps/web/src/stores/useSocAssistantSettingsStore.ts`
- Modify: `apps/web/src/components/settings/AiPreferencesPanel.vue`
- Modify: `apps/web/src/components/settings/SettingsModal.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Replace or modify: `apps/web/tests/unit/aiPreferencesClient.test.ts`

- [ ] **Step 1: Replace client tests**

Replace `apps/web/tests/unit/aiPreferencesClient.test.ts` contents with:

```ts
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getSocAssistantSettings,
  testSocAssistantSettings,
  updateSocAssistantSettings,
} from '../../src/services/socAssistantSettingsClient'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('socAssistantSettingsClient', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('gets enterprise SOC Assistant settings', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        provider: 'anthropic',
        model: 'claude-sonnet-4-6',
        apiKeySet: true,
        configured: true,
        updatedAt: null,
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    const result = await getSocAssistantSettings()

    expect(fetcher).toHaveBeenCalledWith('/api/ai/agent/settings', expect.objectContaining({ credentials: 'include' }))
    expect(result.provider).toBe('anthropic')
    expect(result.apiKeySet).toBe(true)
  })

  it('updates enterprise settings with CSRF header', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_z' }))
      .mockResolvedValueOnce(jsonResponse({
        provider: 'openai',
        model: 'gpt-4o',
        apiKeySet: true,
        configured: true,
        updatedAt: '2026-05-18T00:00:00.000Z',
      }))
    vi.stubGlobal('fetch', fetcher)

    const result = await updateSocAssistantSettings({
      provider: 'openai',
      model: 'gpt-4o',
      apiKey: 'sk-secret',
    })

    const putCall = fetcher.mock.calls[1]
    expect(putCall[0]).toBe('/api/ai/agent/settings')
    expect(putCall[1].method).toBe('PUT')
    expect(putCall[1].headers['X-CSRF-Token']).toBe('csrf_z')
    expect(JSON.parse(putCall[1].body).apiKey).toBe('sk-secret')
    expect(result.configured).toBe(true)
  })

  it('tests enterprise settings with CSRF header', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_z' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, status: 'success', error: null }))
    vi.stubGlobal('fetch', fetcher)

    const result = await testSocAssistantSettings()

    expect(fetcher.mock.calls[1][0]).toBe('/api/ai/agent/settings/test')
    expect(fetcher.mock.calls[1][1].method).toBe('POST')
    expect(result.ok).toBe(true)
  })
})
```

- [ ] **Step 2: Run client tests to verify they fail**

Run:

```bash
cd apps/web && pnpm test -- aiPreferencesClient
```

Expected: FAIL because `socAssistantSettingsClient` does not exist.

- [ ] **Step 3: Create settings client**

Create `apps/web/src/services/socAssistantSettingsClient.ts`:

```ts
import { useAuthStore } from '../stores/useAuthStore'

export type SocAssistantSettings = {
  provider: string
  model: string
  apiKeySet: boolean
  configured: boolean
  lastTestedAt?: string | null
  lastTestStatus?: string | null
  lastTestError?: string | null
  updatedBy?: string | null
  updatedAt?: string | null
}

export type SocAssistantSettingsUpdate = {
  provider?: string
  model?: string
  apiKey?: string
}

export type SocAssistantSettingsTestResult = {
  ok: boolean
  status: string
  error?: string | null
}

async function csrfHeaders(): Promise<Record<string, string>> {
  const auth = useAuthStore()
  if (!auth.csrfToken) await auth.fetchCsrf()
  return { 'X-CSRF-Token': auth.csrfToken }
}

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  const data = await response.json().catch(() => ({}))
  const message = typeof (data as any)?.detail === 'string' ? (data as any).detail : fallback
  throw new Error(message)
}

export async function getSocAssistantSettings(): Promise<SocAssistantSettings> {
  const response = await fetch('/api/ai/agent/settings', { credentials: 'include' })
  return parseOrThrow<SocAssistantSettings>(response, 'Falha ao carregar configuração do Assistente SOC')
}

export async function updateSocAssistantSettings(
  update: SocAssistantSettingsUpdate,
): Promise<SocAssistantSettings> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/settings', {
    method: 'PUT',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
  return parseOrThrow<SocAssistantSettings>(response, 'Falha ao salvar configuração do Assistente SOC')
}

export async function testSocAssistantSettings(): Promise<SocAssistantSettingsTestResult> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/settings/test', {
    method: 'POST',
    credentials: 'include',
    headers,
  })
  return parseOrThrow<SocAssistantSettingsTestResult>(response, 'Falha ao testar Assistente SOC')
}
```

- [ ] **Step 4: Create settings store**

Create `apps/web/src/stores/useSocAssistantSettingsStore.ts`:

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getSocAssistantSettings,
  testSocAssistantSettings,
  updateSocAssistantSettings,
  type SocAssistantSettings,
  type SocAssistantSettingsTestResult,
  type SocAssistantSettingsUpdate,
} from '../services/socAssistantSettingsClient'

export const useSocAssistantSettingsStore = defineStore('socAssistantSettings', () => {
  const settings = ref<SocAssistantSettings | null>(null)
  const testResult = ref<SocAssistantSettingsTestResult | null>(null)
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isTesting = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    isLoading.value = true
    error.value = null
    try {
      settings.value = await getSocAssistantSettings()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }

  async function save(update: SocAssistantSettingsUpdate) {
    isSaving.value = true
    error.value = null
    try {
      settings.value = await updateSocAssistantSettings(update)
      return settings.value
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function testConnection() {
    isTesting.value = true
    error.value = null
    try {
      testResult.value = await testSocAssistantSettings()
      await load()
      return testResult.value
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      isTesting.value = false
    }
  }

  return { settings, testResult, isLoading, isSaving, isTesting, error, load, save, testConnection }
})
```

- [ ] **Step 5: Replace settings panel implementation**

In `apps/web/src/components/settings/AiPreferencesPanel.vue`, replace the script with a SOC Assistant settings script:

```vue
<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { Bot, KeyRound, Save, ShieldCheck } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useSocAssistantSettingsStore } from '../../stores/useSocAssistantSettingsStore'

const { t } = useI18n()
const store = useSocAssistantSettingsStore()
const apiKeyDraft = ref('')
const saved = ref(false)
const form = reactive({
  provider: 'anthropic',
  model: 'claude-sonnet-4-6',
})

const providers = [
  { id: 'anthropic', label: 'Anthropic Claude', defaultModel: 'claude-sonnet-4-6' },
  { id: 'openai', label: 'OpenAI', defaultModel: 'gpt-4o' },
]

onMounted(async () => {
  await store.load()
})

watch(
  () => store.settings,
  (settings) => {
    if (!settings) return
    form.provider = settings.provider || 'anthropic'
    form.model = settings.model || providers.find((item) => item.id === form.provider)?.defaultModel || ''
  },
  { immediate: true, deep: true },
)

function selectProvider(provider: string) {
  form.provider = provider
  const option = providers.find((item) => item.id === provider)
  if (option) form.model = option.defaultModel
}

async function save() {
  await store.save({
    provider: form.provider,
    model: form.model,
    ...(apiKeyDraft.value ? { apiKey: apiKeyDraft.value } : {}),
  })
  apiKeyDraft.value = ''
  saved.value = true
  window.setTimeout(() => (saved.value = false), 2200)
}

async function clearApiKey() {
  await store.save({ apiKey: '' })
  apiKeyDraft.value = ''
}
</script>
```

Replace the template with a provider/model/API-key form. Keep the existing visual density and avoid CLI mode. Use these i18n keys:

```vue
<template>
  <section class="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-2 text-sm">
    <header class="flex items-center gap-2">
      <Bot class="h-5 w-5 text-theme-primary" />
      <div>
        <h3 class="text-lg font-semibold text-theme-text">{{ t('settings.ai.title') }}</h3>
        <p class="text-xs text-theme-text-muted">{{ t('settings.ai.subtitle') }}</p>
      </div>
    </header>

    <p v-if="store.error" class="rounded border border-red-400/40 bg-red-950/20 p-2 text-xs text-red-200">
      {{ store.error }}
    </p>
    <p v-if="saved" class="rounded border border-emerald-400/40 bg-emerald-950/20 p-2 text-xs text-emerald-200">
      {{ t('settings.ai.saved') }}
    </p>

    <fieldset class="flex flex-col gap-3 rounded border border-theme-border p-3">
      <legend class="px-1 text-xs uppercase tracking-wide text-theme-text-muted">{{ t('settings.ai.provider') }}</legend>
      <label
        v-for="provider in providers"
        :key="provider.id"
        class="flex items-start gap-2 rounded border px-2 py-2 transition-colors"
        :class="form.provider === provider.id ? 'border-theme-primary bg-theme-primary/5' : 'border-theme-border'"
      >
        <input
          type="radio"
          name="soc-assistant-provider"
          class="mt-0.5"
          :value="provider.id"
          :checked="form.provider === provider.id"
          @change="selectProvider(provider.id)"
        />
        <span class="text-sm font-medium text-theme-text">{{ provider.label }}</span>
      </label>
    </fieldset>

    <label class="flex flex-col gap-1 text-xs">
      <span class="text-theme-text-muted">{{ t('settings.ai.model') }}</span>
      <input v-model="form.model" type="text" class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm" />
    </label>

    <label class="flex flex-col gap-1 text-xs">
      <span class="text-theme-text-muted">
        {{ t('settings.ai.apiKey') }}
        <span v-if="store.settings?.apiKeySet" class="ml-1 rounded bg-emerald-500/15 px-1 py-0.5 text-[10px] uppercase text-emerald-200">
          {{ t('settings.ai.keySaved') }}
        </span>
      </span>
      <input
        v-model="apiKeyDraft"
        type="password"
        autocomplete="off"
        :aria-label="store.settings?.apiKeySet ? t('settings.ai.keepKeyHint') : 'sk-...'"
        class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm font-mono"
      />
      <p class="text-[11px] text-theme-text-muted">{{ t('settings.ai.keyHelp') }}</p>
      <button v-if="store.settings?.apiKeySet" type="button" class="self-start text-[11px] text-red-300 hover:underline" @click="clearApiKey">
        {{ t('settings.ai.removeKey') }}
      </button>
    </label>

    <div class="rounded border border-theme-border bg-theme-bg/40 p-3 text-xs">
      <div class="flex items-center gap-2 text-theme-text">
        <ShieldCheck class="h-4 w-4 text-theme-primary" />
        <span>{{ store.settings?.configured ? t('settings.ai.configured') : t('settings.ai.notConfigured') }}</span>
      </div>
      <p v-if="store.settings?.lastTestStatus" class="mt-1 text-theme-text-muted">
        {{ t('settings.ai.lastTest') }}: {{ store.settings.lastTestStatus }}
      </p>
    </div>

    <footer class="flex items-center justify-between gap-2 border-t border-theme-border pt-3">
      <button type="button" class="rounded border border-theme-border px-3 py-1.5 text-sm" :disabled="store.isTesting" @click="store.testConnection()">
        {{ store.isTesting ? t('settings.ai.testing') : t('settings.ai.test') }}
      </button>
      <button type="button" class="inline-flex items-center gap-2 rounded bg-theme-primary px-3 py-1.5 text-sm font-medium text-theme-on-primary disabled:opacity-50" :disabled="store.isSaving" @click="save">
        <Save class="h-3 w-3" />
        {{ t('settings.ai.save') }}
      </button>
    </footer>
  </section>
</template>
```

- [ ] **Step 6: Gate Settings tab visibility**

In `apps/web/src/components/settings/SettingsModal.vue`, use `useAuthStore()` if it is not already imported in the component.

Where the AI settings tab is rendered, show it only when:

```ts
authStore.hasPermission('ai.agent.manage')
```

Keep super-admin behavior because `hasPermission()` returns true for admins.

If the tab list is generated from an array, filter the AI item there. If it is hard-coded, wrap the AI tab button and content in the same permission check.

- [ ] **Step 7: Add settings i18n keys**

In both locale files under `settings.ai`, add the keys used above.

`pt-BR`:

```ts
    ai: {
      title: 'Assistente SOC',
      subtitle: 'Configuração empresarial do provider, modelo e chave de API usados pelo Assistente SOC.',
      provider: 'Provider',
      model: 'Modelo',
      apiKey: 'Chave de API',
      keySaved: 'salva',
      keepKeyHint: 'Chave salva, deixe vazio para manter',
      keyHelp: 'A chave é criptografada no servidor e nunca retorna em texto puro.',
      removeKey: 'Remover chave salva',
      configured: 'Assistente configurado',
      notConfigured: 'Assistente não configurado',
      lastTest: 'Último teste',
      testing: 'Testando...',
      test: 'Testar conexão',
      save: 'Salvar',
      saved: 'Configuração salva.',
    },
```

`en-US`:

```ts
    ai: {
      title: 'SOC Assistant',
      subtitle: 'Enterprise provider, model and API key configuration for the SOC Assistant.',
      provider: 'Provider',
      model: 'Model',
      apiKey: 'API key',
      keySaved: 'saved',
      keepKeyHint: 'Key saved, leave blank to keep it',
      keyHelp: 'The key is encrypted on the server and is never returned in plain text.',
      removeKey: 'Remove saved key',
      configured: 'Assistant configured',
      notConfigured: 'Assistant not configured',
      lastTest: 'Last test',
      testing: 'Testing...',
      test: 'Test connection',
      save: 'Save',
      saved: 'Settings saved.',
    },
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd apps/web && pnpm test -- aiPreferencesClient
cd apps/web && pnpm test -- aiAgentStore
```

Expected: PASS.

- [ ] **Step 9: Run frontend build**

Run:

```bash
cd apps/web && pnpm build
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add apps/web/src/services/socAssistantSettingsClient.ts apps/web/src/stores/useSocAssistantSettingsStore.ts apps/web/src/components/settings/AiPreferencesPanel.vue apps/web/src/components/settings/SettingsModal.vue apps/web/src/i18n/messages/pt-BR.ts apps/web/src/i18n/messages/en-US.ts apps/web/tests/unit/aiPreferencesClient.test.ts
git commit -m "feat(web): add enterprise SOC assistant settings"
```

---

### Task 8: Remove Obsolete Backend/CLI Product Paths From UX Surface

**Files:**
- Modify: `apps/web/src/services/aiAgentClient.ts`
- Modify: `apps/web/src/components/ai/AgentPanel.vue`
- Modify: `apps/web/src/components/settings/AiPreferencesPanel.vue`
- Modify: `apps/api/app/routers/ai.py`
- Modify: `apps/api/tests/test_ai_cli_provider.py`
- Modify: `apps/api/tests/test_ai_preferences.py`

- [ ] **Step 1: Confirm no frontend imports of backend/role catalog remain**

Run:

```bash
git grep -n "listBackends\\|listAgentRoles\\|probeCliBinary\\|cliBinary\\|selectedBackend\\|selectedRole" -- apps/web/src apps/web/tests
```

Expected after Tasks 5-7: no matches in product components. Test files may still reference old names only if they are being deleted or rewritten in this task.

- [ ] **Step 2: Remove frontend obsolete exports**

In `apps/web/src/services/aiAgentClient.ts`, remove:

```ts
export async function listBackends()
export async function listAgentRoles()
```

and remove imported usages from `useAiAgentStore.ts`.

In `apps/web/src/services/aiPreferencesClient.ts`, either delete the file if no imports remain or leave it unused for legacy tests removed in Task 7. Prefer deleting only when:

```bash
git grep -n "aiPreferencesClient" -- apps/web/src apps/web/tests
```

returns no matches.

- [ ] **Step 3: Backend CLI remains but product endpoint is deprecated**

Do not delete `apps/api/app/ai/cli_provider.py` in this phase. It has tests and can remain for legacy `/api/ai/preferences`.

In `apps/api/app/routers/ai.py`, mark `/api/ai/preferences/cli/probe` as legacy by adding to the docstring above `probe_cli_binary()`:

```python
"""Legacy diagnostic for per-user CLI preferences.

The product SOC Assistant no longer exposes CLI mode. Keep this endpoint only
for legacy per-user AI preference callers until `/api/ai/chat` is migrated.
"""
```

- [ ] **Step 4: Run grep to confirm product UX has no CLI**

Run:

```bash
git grep -n "Claude Code\\|Codex CLI\\|CLI local\\|API direta\\|probeCliBinary\\|cliBinary" -- apps/web/src
```

Expected: no matches.

- [ ] **Step 5: Run backend legacy preference tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_preferences.py tests/test_ai_cli_provider.py -q
```

Expected: PASS. These tests verify legacy code still works while product UX stops exposing it.

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd apps/web && pnpm test -- aiAgentStore aiPreferencesClient
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/services/aiAgentClient.ts apps/web/src/stores/useAiAgentStore.ts apps/web/src/components/ai/AgentPanel.vue apps/web/src/components/settings/AiPreferencesPanel.vue apps/api/app/routers/ai.py
git add -u apps/web/src/services/aiPreferencesClient.ts
git commit -m "chore(ai): remove CLI and backend selectors from product UX"
```

---

### Task 9: Final Verification For Phase 1

**Files:**
- No source files unless verification uncovers a bug.

- [ ] **Step 1: Run API focused tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ai_agent.py tests/test_ai_agent_settings.py tests/test_roles_rbac.py tests/test_ai_preferences.py tests/test_ai_cli_provider.py -q
```

Expected: PASS.

- [ ] **Step 2: Run API lint**

Run:

```bash
cd apps/api && uv run ruff check app tests
```

Expected: PASS.

- [ ] **Step 3: Run web focused tests**

Run:

```bash
cd apps/web && pnpm test -- aiAgentStore aiPreferencesClient
```

Expected: PASS.

- [ ] **Step 4: Run web build**

Run:

```bash
cd apps/web && pnpm build
```

Expected: PASS.

- [ ] **Step 5: Run repo whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Inspect final product strings**

Run:

```bash
git grep -n "Agente IA\\|AI Agent\\|Backend:\\|CLI local\\|Claude Code\\|Codex CLI" -- apps/web/src
```

Expected: no matches for product UX strings. If tests or comments still mention legacy CLI under backend-only files, keep them out of `apps/web/src`.

- [ ] **Step 7: Commit final fixes if any**

If verification required fixes:

```bash
git add <fixed-files>
git commit -m "fix(ai): stabilize SOC assistant phase 1"
```

If no fixes were needed, do not create an empty commit.

---

## Completion Criteria

Phase 1 is complete when:

- `ai.agent.manage` and `playbooks.manage` appear in the role manager catalog.
- Admins or roles with `ai.agent.manage` can configure one enterprise provider/model/API key.
- The API redacts API keys on every GET/PUT response.
- `/api/ai/agent/sessions` works without frontend `role` or `backend`.
- Missing provider configuration returns a clear not-configured error.
- The SOC Assistant panel shows no backend or role selector.
- Settings no longer exposes Claude/Codex CLI mode.
- Existing legacy per-user AI preference tests still pass until those call sites are migrated.
- Focused API and web tests pass.

## Self-Review Notes

- Spec coverage: this plan covers Phase 1 UX/configuration/routing, adds the two permissions needed by later phases, and keeps legacy `/api/ai/chat` intact.
- Deferred work is explicit: RBAC-driven dashboard tool filtering, playbook graph tools, and legacy preference removal are separate plans.
- No product path uses Claude/Codex CLI after Task 8; backend legacy code remains tested but not visible in web UX.
