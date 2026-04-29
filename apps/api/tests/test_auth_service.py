from datetime import UTC, datetime

from app.auth.keycloak import KeycloakTokenSet, KeycloakUser
from app.auth.service import AuthIdentity, AuthService, KeycloakIdentityProvider
from app.auth.session_store import InMemorySessionStore


class RecordingProvider:
    def __init__(self) -> None:
        self.register_calls: list[tuple[str, str, str]] = []
        self.login_calls: list[tuple[str, str]] = []

    def register(self, *, email: str, password: str, display_name: str) -> AuthIdentity:
        self.register_calls.append((email, password, display_name))
        return AuthIdentity(
            user={
                "id": "usr_01",
                "email": email,
                "displayName": display_name,
                "roles": ["analyst"],
            },
            tokens={
                "access_token": "server-side-access-token",
                "refresh_token": "server-side-refresh-token",
                "expires_in": 300,
            },
        )

    def login(self, *, email: str, password: str) -> AuthIdentity:
        self.login_calls.append((email, password))
        return AuthIdentity(
            user={
                "id": "usr_01",
                "email": email,
                "displayName": "SOC Analyst",
                "roles": ["analyst"],
            },
            tokens={
                "access_token": "server-side-access-token",
                "refresh_token": "server-side-refresh-token",
                "expires_in": 300,
            },
        )


def test_auth_service_register_stores_tokens_server_side_and_returns_public_session():
    provider = RecordingProvider()
    store = InMemorySessionStore(token_factory=lambda: "session_01")
    service = AuthService(provider=provider, session_store=store)

    result = service.register(
        email="analyst@example.com",
        password="correct-horse-battery-staple",
        display_name="SOC Analyst",
    )

    assert provider.register_calls == [
        ("analyst@example.com", "correct-horse-battery-staple", "SOC Analyst")
    ]
    assert result.session_id == "session_01"
    assert result.payload == {
        "user": {
            "id": "usr_01",
            "email": "analyst@example.com",
            "displayName": "SOC Analyst",
            "roles": ["analyst"],
        },
        "session": {
            "authenticated": True,
            "expiresAt": result.payload["session"]["expiresAt"],
        },
    }
    assert "access_token" not in result.payload
    assert store.get("session_01").tokens["access_token"] == "server-side-access-token"


def test_auth_service_login_and_logout_are_session_store_backed():
    provider = RecordingProvider()
    store = InMemorySessionStore(token_factory=lambda: "session_02")
    service = AuthService(provider=provider, session_store=store)

    login_result = service.login(
        email="analyst@example.com",
        password="correct-horse-battery-staple",
    )
    current_user = service.get_current_user(login_result.session_id)
    logout_payload = service.logout(login_result.session_id)

    assert provider.login_calls == [("analyst@example.com", "correct-horse-battery-staple")]
    assert current_user == {
        "id": "usr_01",
        "email": "analyst@example.com",
        "displayName": "SOC Analyst",
        "roles": ["analyst"],
    }
    assert logout_payload == {"authenticated": False}
    assert service.get_current_user(login_result.session_id) is None


def test_auth_service_uses_refresh_token_lifespan_for_browser_session():
    class RefreshTokenProvider(RecordingProvider):
        def login(self, *, email: str, password: str) -> AuthIdentity:
            identity = super().login(email=email, password=password)
            return AuthIdentity(
                user=identity.user,
                tokens={
                    **identity.tokens,
                    "refresh_expires_in": 1800,
                },
            )

    provider = RefreshTokenProvider()
    store = InMemorySessionStore(token_factory=lambda: "session_refresh")
    service = AuthService(provider=provider, session_store=store)

    before_login = datetime.now(UTC)
    login_result = service.login(
        email="analyst@example.com",
        password="correct-horse-battery-staple",
    )

    session = store.get(login_result.session_id)
    assert session is not None
    assert session.expires_at is not None
    assert (session.expires_at - before_login).total_seconds() >= 1700


def test_keycloak_identity_provider_uses_roles_from_server_side_token():
    class FakeKeycloakClient:
        def login(self, *, email: str, password: str) -> KeycloakTokenSet:
            return KeycloakTokenSet(
                access_token="server-side-token",
                refresh_token="server-side-refresh",
                expires_in=300,
                roles=["admin"],
            )

        def get_userinfo(self, *, access_token: str) -> KeycloakUser:
            assert access_token == "server-side-token"
            return KeycloakUser(
                id="usr_admin",
                email="admin@example.com",
                display_name="SOC Admin",
                roles=["analyst"],
            )

    provider = KeycloakIdentityProvider(FakeKeycloakClient())

    identity = provider.login(
        email="admin@example.com",
        password="correct-horse-battery-staple",
    )

    assert identity.user == {
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }
