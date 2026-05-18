"""Autonomous agent endpoints — `/api/ai/agent/*`.

Sits alongside the existing `/api/ai/chat` (single-turn) and lets the
cockpit drive a multi-step tool-using agent. PR1 ships only the
scripted backend; Anthropic/OpenAI backends arrive in PR2/PR3.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.agent import (
    AgentSession,
    ToolContext,
    get_session_store,
    list_tools,
)
from app.ai.agent.backends.base import BackendError, Final
from app.ai.agent.registry import tool_allowed_by_permissions
from app.ai.agent.roles import get_role
from app.ai.agent.router import AgentNotConfiguredError, pick_backend
from app.ai.agent.runner import AgentRunner
from app.ai.agent.settings import (
    SUPPORTED_PROVIDERS,
    get_ai_agent_settings_store,
    normalize_provider,
)

# Importing this module side-effect registers built-in tools.
from app.ai.agent.tools import (  # noqa: F401
    audit_tool,
    capabilities,
    incidents,
    integrations,
    playbook_runs,
    playbooks,
    tickets,
    widgets,
    workspace,
    xdr_endpoints,
)
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.permissions import require_permission, resolve_effective_permissions
from app.db.session import get_db_session
from app.realtime import sse_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-agent"], prefix="/ai/agent")


_API_KEY_MAX_LENGTH = 1024
_PROBE_SYSTEM_PROMPT = (
    "You are validating FortiDashboard SOC Assistant provider connectivity. "
    "Reply with OK only."
)
_PROBE_USER_PROMPT = "Reply with OK."


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    locale: str = Field(default="pt-BR", min_length=2, max_length=16)


class SessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    backend: str
    model: str
    role: str
    locale: str
    created_at: float = Field(alias="createdAt")
    tokens_in: int = Field(alias="tokensIn")
    tokens_out: int = Field(alias="tokensOut")


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ApprovalRequest(BaseModel):
    granted: bool
    reason: str = Field(default="", max_length=500)


class AiAgentSettingsTestResponse(BaseModel):
    ok: bool
    status: str
    error: str | None = None


def _redact_probe_error(message: str, *, api_key: str) -> str:
    text = (message or "SOC Assistant provider probe failed")[:300]
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text


async def _probe_ai_agent_settings(
    *,
    api_key: str,
    user_id: str | None,
) -> AiAgentSettingsTestResponse:
    role = get_role("chat")
    if role is None:
        return AiAgentSettingsTestResponse(
            ok=False,
            status="failed",
            error="agent role registry unavailable",
        )
    backend = pick_backend(role, user_id)
    try:
        async for event in backend.stream_decide(
            history=[{"role": "user", "content": _PROBE_USER_PROMPT}],
            tools=[],
            system_prompt=_PROBE_SYSTEM_PROMPT,
            locale="en-US",
            max_output_tokens=16,
        ):
            if isinstance(event, BackendError):
                return AiAgentSettingsTestResponse(
                    ok=False,
                    status="failed",
                    error=_redact_probe_error(event.message, api_key=api_key),
                )
            if isinstance(event, Final):
                return AiAgentSettingsTestResponse(ok=True, status="success", error=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ai_agent_settings_probe_failed")
        return AiAgentSettingsTestResponse(
            ok=False,
            status="failed",
            error=_redact_probe_error(str(exc), api_key=api_key),
        )
    finally:
        http_client = getattr(backend, "http_client", None)
        if getattr(backend, "_owns_client", False) and hasattr(http_client, "aclose"):
            await http_client.aclose()

    return AiAgentSettingsTestResponse(
        ok=False,
        status="failed",
        error="SOC Assistant provider probe ended without a final response",
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _default_settings_payload() -> dict[str, Any]:
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


def _settings_audit_details(
    settings_payload: dict[str, Any],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "provider": settings_payload.get("provider") or "",
        "model": settings_payload.get("model") or "",
        "credentialSet": bool(settings_payload.get("apiKeySet")),
        "configured": bool(settings_payload.get("configured")),
    }
    if status is not None:
        details["status"] = status
    return details


def _record_settings_audit(
    *,
    audit_store: Any,
    action: str,
    request: Request,
    current_user: dict,
    details: dict[str, Any],
) -> None:
    audit_store.record(
        action=action,
        outcome="success",
        email=current_user.get("email"),
        user_id=current_user.get("id"),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _optional_string_field(
    payload: dict[str, Any],
    field_name: str,
    *,
    max_length: int,
) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
    if len(value) > max_length:
        raise HTTPException(status_code=400, detail=f"{field_name} exceeds maximum length")
    return value


def _build_tool_context(
    *,
    user: dict,
    locale: str,
    audit_store: Any,
    effective_permissions: frozenset[str],
) -> ToolContext:
    # Lazy imports avoid loading service factories at module import time
    # (keeps test patch points stable).
    from app.routers.integrations import get_fortigate_integration_service
    from app.routers.soc import get_siem_client, get_soar_client, get_xdr_client
    from app.routers.widgets import get_fortigate_widget_service
    from app.routers.workspaces import get_workspace_store

    return ToolContext(
        user_id=str(user.get("id") or ""),
        email=user.get("email"),
        locale=locale,
        siem_client=get_siem_client(),
        soar_client=get_soar_client(),
        xdr_client=get_xdr_client(),
        fortigate_widget_service=get_fortigate_widget_service(),
        fortigate_integration_service=get_fortigate_integration_service(),
        workspace_store=get_workspace_store(),
        audit_store=audit_store,
        effective_permissions=effective_permissions,
    )


@router.get("/tools")
def list_agent_tools(
    current_user: Annotated[dict, Depends(get_current_api_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict[str, list[dict[str, Any]]]:
    effective_permissions = frozenset(resolve_effective_permissions(db, current_user))
    return {
        "items": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "category": tool.category,
                "requiresApproval": tool.requires_approval,
                "requiredPermissions": sorted(tool.required_permissions),
                "timeoutSeconds": tool.timeout_seconds,
            }
            for tool in list_tools()
            if tool_allowed_by_permissions(tool, effective_permissions)
        ]
    }


@router.get("/settings")
def get_ai_agent_settings(
    request: Request,
    current_user: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
) -> dict[str, Any]:
    settings = get_ai_agent_settings_store().get()
    payload = _default_settings_payload() if settings is None else settings.to_dict(redact=True)
    _record_settings_audit(
        audit_store=audit_store,
        action="ai.agent.settings.read",
        request=request,
        current_user=current_user,
        details=_settings_audit_details(payload),
    )
    return payload


@router.put("/settings")
def update_ai_agent_settings(
    request: Request,
    payload: Annotated[Any, Body(...)],
    current_user: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="settings payload must be an object")
    fields: dict[str, Any] = {}
    provider_value = _optional_string_field(payload, "provider", max_length=32)
    if provider_value is not None:
        provider = normalize_provider(provider_value)
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"provider '{provider_value}' not supported",
            )
        fields["provider"] = provider
    model_value = _optional_string_field(payload, "model", max_length=128)
    if model_value is not None:
        fields["model"] = model_value.strip()
    api_key = payload.get("apiKey")
    if api_key is not None:
        if not isinstance(api_key, str):
            raise HTTPException(status_code=400, detail="apiKey must be a string")
        if len(api_key) > _API_KEY_MAX_LENGTH:
            raise HTTPException(status_code=400, detail="apiKey exceeds maximum length")
        fields["api_key"] = api_key
    if any(name in fields for name in ("provider", "model", "api_key")):
        fields["last_tested_at"] = None
        fields["last_test_status"] = None
        fields["last_test_error"] = None
    fields["updated_by"] = current_user.get("email") or str(current_user.get("id") or "")
    settings = get_ai_agent_settings_store().upsert(**fields)
    payload = settings.to_dict(redact=True)
    _record_settings_audit(
        audit_store=audit_store,
        action="ai.agent.settings.updated",
        request=request,
        current_user=current_user,
        details={
            key: value
            for key, value in _settings_audit_details(payload).items()
            if key != "configured"
        },
    )
    return payload


@router.post("/settings/test", response_model=AiAgentSettingsTestResponse)
async def test_ai_agent_settings(
    request: Request,
    current_user: Annotated[dict, Depends(require_permission("ai.agent.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> AiAgentSettingsTestResponse:
    store = get_ai_agent_settings_store()
    settings = store.get()
    if settings is None or not settings.configured:
        settings = store.upsert(
            last_tested_at=datetime.now(UTC),
            last_test_status="not_configured",
            last_test_error="SOC Assistant provider is not configured",
            updated_by=current_user.get("email") or str(current_user.get("id") or ""),
        )
        payload = settings.to_dict(redact=True)
        _record_settings_audit(
            audit_store=audit_store,
            action="ai.agent.settings.tested",
            request=request,
            current_user=current_user,
            details=_settings_audit_details(payload, status="not_configured"),
        )
        return AiAgentSettingsTestResponse(
            ok=False,
            status="not_configured",
            error="SOC Assistant provider is not configured",
        )
    probe = await _probe_ai_agent_settings(
        api_key=settings.api_key,
        user_id=str(current_user.get("id") or ""),
    )
    settings = store.upsert(
        last_tested_at=datetime.now(UTC),
        last_test_status=probe.status,
        last_test_error=probe.error,
        updated_by=current_user.get("email") or str(current_user.get("id") or ""),
    )
    _record_settings_audit(
        audit_store=audit_store,
        action="ai.agent.settings.tested",
        request=request,
        current_user=current_user,
        details=_settings_audit_details(settings.to_dict(redact=True), status=probe.status),
    )
    return probe


@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
def create_session(
    payload: Annotated[CreateSessionRequest, Body(...)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> SessionResponse:
    role = get_role("chat")
    if role is None:
        raise HTTPException(status_code=500, detail="agent role registry unavailable")
    try:
        backend = pick_backend(role, str(current_user["id"]))
    except AgentNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store = get_session_store()
    session = store.create(
        user_id=str(current_user["id"]),
        backend=backend.name,
        model=backend.model,
        role_id="soc-assistant",
        locale=payload.locale,
    )
    return SessionResponse(
        session_id=session.id,
        backend=session.backend,
        model=session.model,
        role=session.role_id,
        locale=session.locale,
        created_at=session.created_at,
        tokens_in=session.tokens_in_total,
        tokens_out=session.tokens_out_total,
    )


@router.get("/sessions/{session_id}")
def get_session_state(
    session_id: str,
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict[str, Any]:
    store = get_session_store()
    session = store.get(session_id, user_id=str(current_user["id"]))
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _serialize_session(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> None:
    store = get_session_store()
    if not store.delete(session_id, user_id=str(current_user["id"])):
        raise HTTPException(status_code=404, detail="session not found")
    return None


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: Request,
    payload: Annotated[SendMessageRequest, Body(...)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    db: Annotated[Session, Depends(get_db_session)],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> StreamingResponse:
    store = get_session_store()
    session = store.get(session_id, user_id=str(current_user["id"]))
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.turn_lock.locked():
        raise HTTPException(status_code=409, detail="session already has an active turn")

    runner = AgentRunner(
        session_store=store,
        backend_picker=pick_backend,
        audit_recorder=lambda *, action, outcome, details: audit_store.record(
            action=action,
            outcome=outcome,
            email=current_user.get("email"),
            user_id=current_user.get("id"),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=details,
        ),
    )

    tool_context = _build_tool_context(
        user=current_user,
        locale=session.locale,
        audit_store=audit_store,
        effective_permissions=frozenset(resolve_effective_permissions(db, current_user)),
    )

    async def event_stream():
        # Initial connected event so the client sees the stream open.
        yield sse_message({"type": "connected", "sessionId": session.id})
        async for event in runner.run_turn(
            session=session,
            user_message=payload.content,
            tool_context=tool_context,
        ):
            yield sse_message({"type": "step", **event.to_dict()})
            if await request.is_disconnected():
                return
            # Yield to let the loop interleave when many steps happen quickly.
            await asyncio.sleep(0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/approvals/{call_id}")
async def approve_tool_call(
    session_id: str,
    call_id: str,
    payload: Annotated[ApprovalRequest, Body(...)],
    current_user: Annotated[dict, Depends(require_permission("ai.agent.approve"))],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict[str, Any]:
    store = get_session_store()
    session = store.get(session_id, user_id=str(current_user["id"]))
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    future = session.pending_approvals.get(call_id)
    if future is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if future.done():
        raise HTTPException(status_code=409, detail="approval already resolved")
    future.set_result({"granted": payload.granted, "reason": payload.reason})
    return {"sessionId": session.id, "callId": call_id, "granted": payload.granted}


def _serialize_session(session: AgentSession) -> dict[str, Any]:
    return {
        "sessionId": session.id,
        "backend": session.backend,
        "model": session.model,
        "role": session.role_id,
        "locale": session.locale,
        "createdAt": session.created_at,
        "lastUsedAt": session.last_used_at,
        "usedTools": list(session.used_tools),
        "tokensIn": session.tokens_in_total,
        "tokensOut": session.tokens_out_total,
        "pendingApprovals": sorted(session.pending_approvals.keys()),
        "history": [
            {
                "role": m.role,
                "content": m.content,
                "toolCallId": m.tool_call_id,
                "toolName": m.tool_name,
                "toolArgs": m.tool_args,
                "toolResult": m.tool_result,
                "toolCalls": m.tool_calls,
                "createdAt": m.created_at,
            }
            for m in session.history
        ],
    }
