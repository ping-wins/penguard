from dataclasses import dataclass
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True)
class KeycloakTokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class KeycloakUser:
    id: str
    email: str
    display_name: str
    roles: list[str]


class KeycloakClient:
    def __init__(
        self,
        *,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.http_client = http_client or httpx.Client(timeout=10)

    def login(self, *, email: str, password: str) -> KeycloakTokenSet:
        response = self.http_client.post(
            self._realm_url("protocol/openid-connect/token"),
            data={
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": email,
                "password": password,
                "scope": "openid profile email",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return KeycloakTokenSet(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload["expires_in"],
        )

    def create_user(self, *, email: str, password: str, display_name: str) -> KeycloakUser:
        admin_token = self._service_account_access_token()
        response = self.http_client.post(
            self._admin_url("users"),
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": False,
                "firstName": display_name,
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            },
        )
        response.raise_for_status()
        user_id = response.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        return KeycloakUser(
            id=user_id or email,
            email=email,
            display_name=display_name,
            roles=["analyst"],
        )

    def get_userinfo(self, *, access_token: str) -> KeycloakUser:
        response = self.http_client.get(
            self._realm_url("protocol/openid-connect/userinfo"),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()
        display_name = (
            payload.get("name")
            or payload.get("preferred_username")
            or payload["email"]
        )
        return KeycloakUser(
            id=payload["sub"],
            email=payload["email"],
            display_name=display_name,
            roles=["analyst"],
        )

    def _service_account_access_token(self) -> str:
        response = self.http_client.post(
            self._realm_url("protocol/openid-connect/token"),
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _realm_url(self, path: str) -> str:
        return urljoin(self.base_url, f"realms/{self.realm}/{path}")

    def _admin_url(self, path: str) -> str:
        return urljoin(self.base_url, f"admin/realms/{self.realm}/{path}")
