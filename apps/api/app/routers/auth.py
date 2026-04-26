from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.csrf import CsrfGuard
from app.auth.dependencies import (
    get_auth_audit_store,
    get_auth_rate_limiter,
    get_auth_service,
    get_csrf_guard,
)
from app.auth.rate_limit import InMemoryRateLimiter
from app.core.config import get_settings

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(alias="displayName", min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


AuthAuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore
CSRF_GUARD_DEP = Depends(get_csrf_guard)
AUTH_AUDIT_STORE_DEP = Depends(get_auth_audit_store)
AUTH_RATE_LIMITER_DEP = Depends(get_auth_rate_limiter)


def require_csrf(
    request: Request,
    csrf_guard: CsrfGuard = CSRF_GUARD_DEP,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
) -> None:
    try:
        csrf_guard.validate(request)
    except HTTPException:
        audit_store.record(
            action=auth_action(request),
            outcome="csrf_failed",
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        raise


def require_auth_rate_limit(
    request: Request,
    limiter: InMemoryRateLimiter = AUTH_RATE_LIMITER_DEP,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
) -> None:
    action = auth_action(request)
    if limiter.allow(f"{client_ip(request)}:{action}"):
        return
    audit_store.record(
        action=action,
        outcome="rate_limited",
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many authentication attempts",
    )


def auth_action(request: Request) -> str:
    return request.url.path.rstrip("/").rsplit("/", 1)[-1]


def client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


REQUIRE_CSRF_DEP = Depends(require_csrf)
REQUIRE_AUTH_RATE_LIMIT_DEP = Depends(require_auth_rate_limit)


@router.get("/auth/csrf")
def issue_csrf_token(
    response: Response,
    csrf_guard: CsrfGuard = CSRF_GUARD_DEP,
) -> dict[str, str]:
    csrf_token = csrf_guard.issue_token(response)
    return {"csrfToken": csrf_token}


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    _csrf: None = REQUIRE_CSRF_DEP,
    _rate_limit: None = REQUIRE_AUTH_RATE_LIMIT_DEP,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
) -> dict:
    result = get_auth_service().register(
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
    )
    audit_store.record(
        action="register",
        outcome="success",
        email=str(payload.email),
        user_id=result.payload["user"]["id"],
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, result.session_id)
    return result.payload


@router.post("/auth/login")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    _csrf: None = REQUIRE_CSRF_DEP,
    _rate_limit: None = REQUIRE_AUTH_RATE_LIMIT_DEP,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
) -> dict:
    result = get_auth_service().login(
        email=str(payload.email),
        password=payload.password,
    )
    audit_store.record(
        action="login",
        outcome="success",
        email=str(payload.email),
        user_id=result.payload["user"]["id"],
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, result.session_id)
    return result.payload


@router.get("/auth/me")
def get_current_session(request: Request) -> dict:
    settings = get_settings()
    user = get_auth_service().get_current_user(request.cookies.get(settings.session_cookie_name))
    if user is None:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    _csrf: None = REQUIRE_CSRF_DEP,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
) -> dict:
    settings = get_settings()
    auth_service = get_auth_service()
    session_id = request.cookies.get(settings.session_cookie_name)
    user = auth_service.get_current_user(session_id)
    payload = auth_service.logout(session_id)
    audit_store.record(
        action="logout",
        outcome="success",
        email=user["email"] if user else None,
        user_id=user["id"] if user else None,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return payload
