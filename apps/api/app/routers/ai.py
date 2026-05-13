"""AI assistant chat endpoints.

`GET /api/ai/status` is a cheap diagnostic — the cockpit (and humans poking
at the API) can verify which adapter is wired without sending a real prompt.

`POST /api/ai/chat` is the conversational endpoint the sidebar chat box
talks to. Every call audits the user + prompt length so a runaway
integration is visible in the audit trail before it shows up on the API
provider's invoice.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.ai import get_ai_provider
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.core.config import get_settings


router = APIRouter(tags=["ai"])


class ChatTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str
    provider: str
    model: str


class AIStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    model: str
    ready: bool


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _locale_from_request(
    explicit: str | None,
    accept_language: str | None,
) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    if accept_language and accept_language.lower().startswith("en"):
        return "en-US"
    return "pt-BR"


@router.get("/ai/status", response_model=AIStatusResponse)
def ai_status(
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> AIStatusResponse:
    """Return which AI provider/model is wired and whether the API key
    looks present. The cockpit Settings panel can hit this to confirm the
    Anthropic / Gemini / scripted switch took effect after a `.env` edit.
    """
    settings = get_settings()
    provider_name = (settings.ai_provider or "scripted").lower()
    model = settings.ai_model or ""
    if provider_name == "anthropic":
        model = model or "claude-3-5-haiku-latest"
    elif provider_name in {"openai", "openai_compat", "openai-compatible"}:
        model = model or "gpt-4o-mini"
    ready = provider_name == "scripted" or bool(settings.ai_api_key)
    return AIStatusResponse(provider=provider_name, model=model, ready=ready)


@router.post("/ai/chat", response_model=ChatResponse)
def ai_chat(
    request: Request,
    payload: Annotated[ChatRequest, Body(...)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    locale_header: Annotated[
        str | None, Header(alias="X-FortiDashboard-Locale")
    ] = None,
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None,
) -> ChatResponse:
    provider = get_ai_provider()
    locale = _locale_from_request(locale_header, accept_language)
    messages: list[dict[str, str]] = [
        {"role": turn.role, "content": turn.content} for turn in payload.messages
    ]
    last_user = next(
        (turn for turn in reversed(payload.messages) if turn.role == "user"),
        None,
    )
    prompt_len = len(last_user.content) if last_user else 0

    try:
        reply = provider.chat(messages, locale=locale)
    except Exception as exc:  # noqa: BLE001
        audit_store.record(
            action="ai.chat",
            outcome="failure",
            email=current_user.get("email"),
            user_id=current_user.get("id"),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={
                "provider": getattr(provider, "name", "unknown"),
                "promptLength": prompt_len,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider call failed: {exc}",
        ) from exc

    audit_store.record(
        action="ai.chat",
        outcome="success",
        email=current_user.get("email"),
        user_id=current_user.get("id"),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "provider": getattr(provider, "name", "unknown"),
            "promptLength": prompt_len,
            "replyLength": len(reply),
            "locale": locale,
        },
    )

    settings = get_settings()
    return ChatResponse(
        reply=reply,
        provider=getattr(provider, "name", "scripted"),
        model=settings.ai_model or "",
    )
