from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.auth.keycloak import KeycloakClient, KeycloakUser
from app.auth.session_store import SessionRecord
from app.core.fixtures import load_fixture


@dataclass(frozen=True)
class AuthIdentity:
    user: dict[str, Any]
    tokens: dict[str, Any]
    expires_at: str | None = None


@dataclass(frozen=True)
class AuthSessionResult:
    session_id: str
    payload: dict[str, Any]


class IdentityProvider(Protocol):
    def register(self, *, email: str, password: str, display_name: str) -> AuthIdentity:
        pass

    def login(self, *, email: str, password: str) -> AuthIdentity:
        pass

    def sso_exchange(self, *, code: str, redirect_uri: str) -> AuthIdentity:
        pass


class SessionStore(Protocol):
    def create(
        self,
        *,
        user: dict[str, Any],
        tokens: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> str:
        pass

    def get(self, session_id: str | None) -> SessionRecord | None:
        pass

    def delete(self, session_id: str | None) -> None:
        pass


class MockIdentityProvider:
    def register(self, *, email: str, password: str, display_name: str) -> AuthIdentity:
        payload = load_fixture("auth_register_response")
        return AuthIdentity(
            user=payload["user"],
            tokens={
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_in": 7200,
                "refresh_expires_in": 7200,
            },
            expires_at=payload["session"]["expiresAt"],
        )

    def login(self, *, email: str, password: str) -> AuthIdentity:
        payload = load_fixture("auth_login_response")
        return AuthIdentity(
            user=payload["user"],
            tokens={
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_in": 7200,
                "refresh_expires_in": 7200,
            },
            expires_at=payload["session"]["expiresAt"],
        )

    def sso_exchange(self, *, code: str, redirect_uri: str) -> AuthIdentity:
        payload = load_fixture("auth_login_response")
        return AuthIdentity(
            user=payload["user"],
            tokens={
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "expires_in": 7200,
            },
            expires_at=payload["session"]["expiresAt"],
        )


class KeycloakIdentityProvider:
    def __init__(self, keycloak: KeycloakClient) -> None:
        self.keycloak = keycloak

    def register(self, *, email: str, password: str, display_name: str) -> AuthIdentity:
        user = self.keycloak.create_user(email=email, password=password, display_name=display_name)
        tokens = self.keycloak.login(email=email, password=password)
        return AuthIdentity(user=self._public_user(user), tokens=tokens.__dict__)

    def login(self, *, email: str, password: str) -> AuthIdentity:
        tokens = self.keycloak.login(email=email, password=password)
        user = self.keycloak.get_userinfo(access_token=tokens.access_token)
        return AuthIdentity(
            user=self._public_user(user, roles=tokens.roles or ["analyst"]),
            tokens=tokens.__dict__,
        )

    def sso_exchange(self, *, code: str, redirect_uri: str) -> AuthIdentity:
        tokens = self.keycloak.exchange_code(code=code, redirect_uri=redirect_uri)
        user = self.keycloak.get_userinfo(access_token=tokens.access_token)
        return AuthIdentity(
            user=self._public_user(user, roles=tokens.roles or ["analyst"]),
            tokens=tokens.__dict__,
        )

    def _public_user(
        self,
        user: KeycloakUser,
        *,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
            "roles": roles or user.roles,
        }


class AuthService:
    def __init__(self, *, provider: IdentityProvider, session_store: SessionStore) -> None:
        self.provider = provider
        self.session_store = session_store

    def register(self, *, email: str, password: str, display_name: str) -> AuthSessionResult:
        identity = self.provider.register(email=email, password=password, display_name=display_name)
        return self._create_public_session(identity)

    def login(self, *, email: str, password: str) -> AuthSessionResult:
        identity = self.provider.login(email=email, password=password)
        return self._create_public_session(identity)

    def sso_login(self, *, code: str, redirect_uri: str) -> AuthSessionResult:
        identity = self.provider.sso_exchange(code=code, redirect_uri=redirect_uri)
        return self._create_public_session(identity)

    def get_current_user(self, session_id: str | None) -> dict[str, Any] | None:
        session = self.session_store.get(session_id)
        if session is None:
            return None
        return session.user

    def logout(self, session_id: str | None) -> dict[str, bool]:
        self.session_store.delete(session_id)
        return load_fixture("auth_logout_response")

    def _create_public_session(self, identity: AuthIdentity) -> AuthSessionResult:
        expires_at = self._expires_at_datetime(identity.tokens)
        session_id = self.session_store.create(
            user=identity.user,
            tokens=identity.tokens,
            expires_at=expires_at,
        )
        return AuthSessionResult(
            session_id=session_id,
            payload={
                "user": identity.user,
                "session": {
                    "authenticated": True,
                    "expiresAt": identity.expires_at or self._format_expires_at(expires_at),
                },
            },
        )

    def _expires_at_datetime(self, tokens: dict[str, Any]) -> datetime:
        ttl_seconds = self._session_ttl_seconds(tokens)
        return datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    def _session_ttl_seconds(self, tokens: dict[str, Any]) -> int:
        if tokens.get("refresh_token") and tokens.get("refresh_expires_in") is not None:
            return int(tokens["refresh_expires_in"])
        return int(tokens.get("expires_in", 0))

    def _format_expires_at(self, expires_at: datetime) -> str:
        return expires_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
