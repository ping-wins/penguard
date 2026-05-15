from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.auth.audit import (
    AuditSiemForwarder,
    ForwardingAuthAuditStore,
    InMemoryAuthAuditStore,
    SqlAlchemyAuthAuditStore,
)
from app.auth.csrf import CsrfGuard
from app.auth.keycloak import KeycloakClient
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.service import AuthService, KeycloakIdentityProvider, MockIdentityProvider
from app.auth.session_store import InMemorySessionStore, SqlAlchemySessionStore
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.core.fixtures import load_fixture
from app.realtime import realtime_broker
from app.soc.client import SocServiceClient


@lru_cache
def get_csrf_guard() -> CsrfGuard:
    return CsrfGuard()


@lru_cache
def get_auth_rate_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )


@lru_cache
def get_auth_audit_store() -> (
    InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore | ForwardingAuthAuditStore
):
    settings = get_settings()
    if settings.mock_mode:
        return InMemoryAuthAuditStore()
    primary = SqlAlchemyAuthAuditStore(database_url=settings.database_url)
    siem_client = SocServiceClient(
        base_url=settings.siem_kowalski_url,
        service_name="siem_kowalski",
        timeout_seconds=settings.internal_service_timeout_seconds,
    )
    return ForwardingAuthAuditStore(
        primary=primary,
        forwarder=AuditSiemForwarder(
            siem_client=siem_client,
            realtime_publisher=realtime_broker.publish_all,
        ),
    )


@lru_cache
def get_session_store() -> InMemorySessionStore | SqlAlchemySessionStore:
    settings = get_settings()
    if settings.mock_mode:
        return InMemorySessionStore()
    return SqlAlchemySessionStore(
        database_url=settings.database_url,
        token_cipher=TokenCipher.from_secret(settings.token_encryption_key or settings.secret_key),
    )


@lru_cache
def get_auth_service() -> AuthService:
    settings = get_settings()
    if settings.mock_mode:
        provider = MockIdentityProvider()
    else:
        provider = KeycloakIdentityProvider(
            KeycloakClient(
                base_url=settings.keycloak_base_url,
                browser_base_url=settings.keycloak_browser_base_url,
                realm=settings.keycloak_realm,
                client_id=settings.keycloak_client_id,
                client_secret=settings.keycloak_client_secret,
                verify_ssl=settings.keycloak_verify_ssl,
            )
        )
    return AuthService(provider=provider, session_store=get_session_store())


def get_current_api_user(request: Request) -> dict[str, Any]:
    settings = get_settings()
    if settings.mock_mode:
        return dict(load_fixture("auth_me_authenticated")["user"])

    user = get_auth_service().get_current_user(request.cookies.get(settings.session_cookie_name))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


CURRENT_API_USER_DEP = Depends(get_current_api_user)


def require_admin_user(
    current_user: dict[str, Any] = CURRENT_API_USER_DEP,
) -> dict[str, Any]:
    roles = current_user.get("roles") or []
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user
