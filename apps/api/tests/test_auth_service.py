from app.auth.service import AuthIdentity, AuthService
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
