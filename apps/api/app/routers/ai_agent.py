"""Autonomous agent endpoints — `/api/ai/agent/*`.

Sits alongside the existing `/api/ai/chat` (single-turn) and lets the
cockpit drive a multi-step tool-using agent. PR1 ships only the
scripted backend; Anthropic/OpenAI backends arrive in PR2/PR3.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.ai.agent import (
    AgentSession,
    ToolContext,
    get_session_store,
    list_tools,
)
from app.ai.agent.backends import ScriptedBackend
# Importing this module side-effect registers the 9 read tools.
from app.ai.agent.tools import (  # noqa: F401
    audit_tool,
    incidents,
    integrations,
    playbook_runs,
    widgets,
    workspace,
    xdr_endpoints,
)
from app.ai.agent.runner import AgentRunner
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.realtime import sse_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-agent"], prefix="/ai/agent")


_AVAILABLE_BACKENDS = ("scripted",)


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    backend: str = Field(default="scripted", min_length=1, max_length=32)
    locale: str = Field(default="pt-BR", min_length=2, max_length=16)
    model: str = Field(default="", max_length=128)


class SessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    backend: str
    model: str
    locale: str
    created_at: float = Field(alias="createdAt")


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


def _resolve_backend(name: str) -> Any:
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
            {"name": name, "ready": True, "default": name == "scripted"}
            for name in _AVAILABLE_BACKENDS
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


@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
def create_session(
    payload: Annotated[CreateSessionRequest, Body(...)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> SessionResponse:
    if payload.backend not in _AVAILABLE_BACKENDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"backend '{payload.backend}' not available",
        )
    store = get_session_store()
    session = store.create(
        user_id=str(current_user["id"]),
        backend=payload.backend,
        model=payload.model,
        locale=payload.locale,
    )
    return SessionResponse(
        session_id=session.id,
        backend=session.backend,
        model=session.model,
        locale=session.locale,
        created_at=session.created_at,
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

    backend = _resolve_backend(session.backend)
    runner = AgentRunner(
        backend=backend,
        session_store=store,
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


def _serialize_session(session: AgentSession) -> dict[str, Any]:
    return {
        "sessionId": session.id,
        "backend": session.backend,
        "model": session.model,
        "locale": session.locale,
        "createdAt": session.created_at,
        "lastUsedAt": session.last_used_at,
        "usedTools": list(session.used_tools),
        "history": [
            {
                "role": m.role,
                "content": m.content,
                "toolCallId": m.tool_call_id,
                "toolName": m.tool_name,
                "toolArgs": m.tool_args,
                "toolResult": m.tool_result,
                "createdAt": m.created_at,
            }
            for m in session.history
        ],
    }
