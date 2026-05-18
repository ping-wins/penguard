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

from app.ai.agent import (
    AgentSession,
    ToolContext,
    get_session_store,
    list_roles,
    list_tools,
)
from app.ai.agent.backends import ScriptedBackend
from app.ai.agent.roles import get_role
from app.ai.agent.router import pick_backend
from app.ai.agent.runner import AgentRunner
from app.ai.agent.settings import (
    SUPPORTED_PROVIDERS,
    get_ai_agent_settings_store,
    normalize_provider,
)

# Importing this module side-effect registers the 9 read tools.
from app.ai.agent.tools import (  # noqa: F401
    audit_tool,
    capabilities,
    incidents,
    integrations,
    playbook_runs,
    widgets,
    workspace,
    xdr_endpoints,
)
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.permissions import require_permission
from app.realtime import sse_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-agent"], prefix="/ai/agent")


_AVAILABLE_BACKENDS = ("scripted", "anthropic", "openai")


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: str = Field(default="chat", min_length=1, max_length=64)
    backend: str | None = Field(default=None, min_length=1, max_length=32)
    locale: str = Field(default="pt-BR", min_length=2, max_length=16)
    model: str = Field(default="", max_length=128)


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


class AgentRoleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    description: str
    tier: str
    locale_default: str = Field(alias="localeDefault")
    token_budget: int = Field(alias="tokenBudget")
    max_steps: int = Field(alias="maxSteps")
    allowed_tool_categories: list[str] = Field(alias="allowedToolCategories")


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ApprovalRequest(BaseModel):
    granted: bool
    reason: str = Field(default="", max_length=500)


class AiAgentSettingsUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, alias="apiKey", max_length=1024)


class AiAgentSettingsTestResponse(BaseModel):
    ok: bool
    status: str
    error: str | None = None


def _resolve_forced_backend(name: str | None) -> Any | None:
    if name is None:
        return None
    if name == "scripted":
        return ScriptedBackend()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"backend '{name}' not available; configured backends: {list(_AVAILABLE_BACKENDS)}",
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _build_tool_context(*, user: dict, locale: str, audit_store: Any) -> ToolContext:
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
    )


@router.get("/backends")
def list_backends(
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "items": [
            {"name": name, "ready": name == "scripted", "default": name == "scripted"}
            for name in _AVAILABLE_BACKENDS
        ]
    }


@router.get("/roles")
def list_agent_roles(
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict[str, list[AgentRoleResponse]]:
    return {
        "items": [
            AgentRoleResponse(
                id=role.id,
                label=role.label,
                description=role.description,
                tier=role.tier,
                locale_default=role.locale_default,
                token_budget=role.token_budget,
                max_steps=role.max_steps,
                allowed_tool_categories=sorted(role.allowed_tool_categories),
            )
            for role in list_roles()
        ]
    }


@router.get("/tools")
def list_agent_tools(
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "items": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "category": tool.category,
                "requiresApproval": tool.requires_approval,
                "timeoutSeconds": tool.timeout_seconds,
            }
            for tool in list_tools()
        ]
    }


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
            raise HTTPException(
                status_code=400,
                detail=f"provider '{payload.provider}' not supported",
            )
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


@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
def create_session(
    payload: Annotated[CreateSessionRequest, Body(...)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> SessionResponse:
    role = get_role(payload.role)
    if role is None:
        raise HTTPException(status_code=400, detail=f"unknown agent role: {payload.role}")
    forced_backend = _resolve_forced_backend(payload.backend)
    backend = forced_backend or pick_backend(role, str(current_user["id"]))
    store = get_session_store()
    session = store.create(
        user_id=str(current_user["id"]),
        backend=backend.name,
        model=payload.model or backend.model,
        role_id=role.id,
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
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> StreamingResponse:
    store = get_session_store()
    session = store.get(session_id, user_id=str(current_user["id"]))
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.turn_lock.locked():
        raise HTTPException(status_code=409, detail="session already has an active turn")

    backend = ScriptedBackend() if session.backend == "scripted" else None
    runner = AgentRunner(
        session_store=store,
        backend=backend,
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
        user=current_user, locale=session.locale, audit_store=audit_store
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
