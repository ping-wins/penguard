from functools import lru_cache

from app.auth.keycloak import KeycloakClient
from app.auth.service import AuthService, KeycloakIdentityProvider, MockIdentityProvider
from app.auth.session_store import InMemorySessionStore
from app.core.config import get_settings


@lru_cache
def get_session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@lru_cache
def get_auth_service() -> AuthService:
    settings = get_settings()
    if settings.mock_mode:
        provider = MockIdentityProvider()
    else:
        provider = KeycloakIdentityProvider(
            KeycloakClient(
                base_url=settings.keycloak_base_url,
                realm=settings.keycloak_realm,
                client_id=settings.keycloak_client_id,
                client_secret=settings.keycloak_client_secret,
            )
        )
    return AuthService(provider=provider, session_store=get_session_store())
