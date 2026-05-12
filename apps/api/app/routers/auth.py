import logging
from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.csrf import CsrfGuard
from app.auth.dependencies import (
    get_auth_audit_store,
    get_auth_rate_limiter,
    get_auth_service,
    get_csrf_guard,
)
from app.auth.errors import AuthProviderError
from app.auth.keycloak import KeycloakClient
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.service import AuthService
from app.core.config import get_settings

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


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
AUTH_SERVICE_DEP = Depends(get_auth_service)


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
        httponly=settings.session_cookie_httponly,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def raise_auth_provider_error(
    *,
    error: AuthProviderError,
    request: Request,
    action: str,
    audit_store: AuthAuditStore,
    email: str | None = None,
) -> None:
    audit_store.record(
        action=action,
        outcome=error.audit_outcome,
        email=email,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    raise HTTPException(status_code=error.status_code, detail=error.detail)


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
    auth_service: AuthService = AUTH_SERVICE_DEP,
) -> dict:
    email = str(payload.email)
    try:
        result = auth_service.register(
            email=email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except AuthProviderError as error:
        raise_auth_provider_error(
            error=error,
            request=request,
            action="register",
            audit_store=audit_store,
            email=email,
        )
    audit_store.record(
        action="register",
        outcome="success",
        email=email,
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
    auth_service: AuthService = AUTH_SERVICE_DEP,
) -> dict:
    email = str(payload.email)
    try:
        result = auth_service.login(
            email=email,
            password=payload.password,
        )
    except AuthProviderError as error:
        raise_auth_provider_error(
            error=error,
            request=request,
            action="login",
            audit_store=audit_store,
            email=email,
        )
    audit_store.record(
        action="login",
        outcome="success",
        email=email,
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


def sso_failure_redirect(reason: str) -> RedirectResponse:
    settings = get_settings()
    target = settings.sso_failure_redirect_url
    separator = "&" if "?" in target else "?"
    url = f"{target}{separator}{urlencode({'sso_error': reason})}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/sso/kerberos/init")
def sso_kerberos_init(request: Request) -> RedirectResponse:
    settings = get_settings()
    if settings.mock_mode:
        return sso_failure_redirect("mock_mode")
    try:
        keycloak = KeycloakClient(
            base_url=settings.keycloak_base_url,
            browser_base_url=settings.keycloak_browser_base_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
            verify_ssl=settings.keycloak_verify_ssl,
        )
        state = token_urlsafe(24)
        auth_url = keycloak.authorization_url(
            redirect_uri=settings.sso_redirect_uri,
            state=state,
            kc_idp_hint=request.query_params.get("kc_idp_hint"),
        )
        request.session["sso_state"] = state
        return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    except Exception as exc:
        logger.exception("SSO init failed: %s", exc)
        return sso_failure_redirect("unavailable")


@router.get("/auth/sso/kerberos/callback")
def sso_kerberos_callback(
    request: Request,
    audit_store: AuthAuditStore = AUTH_AUDIT_STORE_DEP,
    auth_service: AuthService = AUTH_SERVICE_DEP,
) -> RedirectResponse:
    settings = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    stored_state = request.session.pop("sso_state", None)
    provider_error = request.query_params.get("error")
    if provider_error:
        audit_store.record(
            action="sso_kerberos",
            outcome=f"idp_error:{provider_error}",
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return sso_failure_redirect("unavailable")
    if not code or not state or stored_state is None or state != stored_state:
        audit_store.record(
            action="sso_kerberos",
            outcome="state_mismatch",
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return sso_failure_redirect("state_mismatch")
    try:
        result = auth_service.sso_login(
            code=code,
            redirect_uri=settings.sso_redirect_uri,
        )
    except AuthProviderError as error:
        audit_store.record(
            action="sso_kerberos",
            outcome=error.audit_outcome,
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return sso_failure_redirect("unavailable")
    except Exception as exc:
        logger.exception("SSO callback failed: %s", exc)
        audit_store.record(
            action="sso_kerberos",
            outcome="callback_error",
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return sso_failure_redirect("unavailable")
    audit_store.record(
        action="sso_kerberos",
        outcome="success",
        email=result.payload["user"]["email"],
        user_id=result.payload["user"]["id"],
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response = RedirectResponse(
        url=settings.sso_post_login_url,
        status_code=status.HTTP_302_FOUND,
    )
    set_session_cookie(response, result.session_id)
    return response


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
        httponly=settings.session_cookie_httponly,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
    )
    return payload
