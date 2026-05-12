import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode, urljoin

import httpx

from app.auth.errors import AuthProviderError

FORTIDASHBOARD_REALM_ROLES = ("admin", "analyst")


@dataclass(frozen=True)
class KeycloakTokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int
    refresh_expires_in: int | None = None
    roles: list[str] | None = None


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
        browser_base_url: str | None = None,
        verify_ssl: bool = True,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.browser_base_url = (browser_base_url or base_url).rstrip("/") + "/"
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.http_client = http_client or httpx.Client(timeout=10, verify=verify_ssl)

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        kc_idp_hint: str | None = None,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if kc_idp_hint:
            params["kc_idp_hint"] = kc_idp_hint
        path = f"realms/{self.realm}/protocol/openid-connect/auth"
        return urljoin(self.browser_base_url, path) + "?" + urlencode(params)

    def exchange_code(self, *, code: str, redirect_uri: str) -> KeycloakTokenSet:
        response = self._post_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            context="login",
        )
        payload = response.json()
        return KeycloakTokenSet(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload["expires_in"],
        )

    def login(self, *, email: str, password: str) -> KeycloakTokenSet:
        response = self._post_token(
            {
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": email,
                "password": password,
                "scope": "openid profile email",
            },
            context="login",
        )
        payload = response.json()
        return KeycloakTokenSet(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload["expires_in"],
            refresh_expires_in=payload.get("refresh_expires_in"),
            roles=self._realm_roles(payload["access_token"]),
        )

    def create_user(self, *, email: str, password: str, display_name: str) -> KeycloakUser:
        admin_token = self._service_account_access_token()
        first_name, last_name = self._split_display_name(display_name)
        response = self._request(
            "POST",
            self._admin_url("users"),
            context="create_user",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "firstName": first_name,
                "lastName": last_name,
                "requiredActions": [],
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            },
        )
        self._raise_for_status(response, context="create_user")
        user_id = response.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        return KeycloakUser(
            id=user_id or email,
            email=email,
            display_name=display_name,
            roles=["analyst"],
        )

    def get_userinfo(self, *, access_token: str) -> KeycloakUser:
        response = self._request(
            "GET",
            self._realm_url("protocol/openid-connect/userinfo"),
            context="userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self._raise_for_status(response, context="userinfo")
        payload = response.json()
        sub = payload.get("sub") or payload.get("preferred_username") or "kerberos-user"
        preferred_username = payload.get("preferred_username") or ""
        email = (
            payload.get("email")
            or (preferred_username if "@" in preferred_username else None)
            or (
                f"{preferred_username}@fortidashboard.local"
                if preferred_username
                else f"{sub}@fortidashboard.local"
            )
        )
        display_name = (
            payload.get("name")
            or " ".join(
                part for part in (payload.get("given_name"), payload.get("family_name")) if part
            )
            or preferred_username
            or email
        )
        return KeycloakUser(
            id=sub,
            email=email,
            display_name=display_name,
            roles=["analyst"],
        )

    def _service_account_access_token(self) -> str:
        response = self._post_token(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            context="service_account",
        )
        return response.json()["access_token"]

    def _realm_roles(self, access_token: str) -> list[str]:
        try:
            encoded_payload = access_token.split(".")[1]
            padding = "=" * (-len(encoded_payload) % 4)
            payload = json.loads(base64.urlsafe_b64decode(encoded_payload + padding))
        except (IndexError, ValueError, json.JSONDecodeError):
            return ["analyst"]

        roles = payload.get("realm_access", {}).get("roles", [])
        if not isinstance(roles, list):
            return ["analyst"]

        product_roles = [
            role for role in roles if isinstance(role, str) and role in FORTIDASHBOARD_REALM_ROLES
        ]
        return product_roles or ["analyst"]

    def _split_display_name(self, display_name: str) -> tuple[str, str]:
        parts = display_name.strip().split(maxsplit=1)
        if not parts:
            return ("SOC", "Analyst")
        if len(parts) == 1:
            return (parts[0], parts[0])
        return (parts[0], parts[1])

    def _post_token(self, data: dict[str, str], *, context: str) -> httpx.Response:
        return self._request(
            "POST",
            self._realm_url("protocol/openid-connect/token"),
            context=context,
            data=data,
        )

    def _request(self, method: str, url: str, *, context: str, **kwargs) -> httpx.Response:
        try:
            response = self.http_client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise AuthProviderError(
                status_code=503,
                detail="Identity provider unavailable",
                audit_outcome="provider_unavailable",
            ) from exc
        self._raise_for_status(response, context=context)
        return response

    def _raise_for_status(self, response: httpx.Response, *, context: str) -> None:
        if response.status_code < 400:
            return

        if context == "login" and response.status_code in {400, 401}:
            raise AuthProviderError(status_code=401, detail="Invalid email or password")

        if context == "create_user" and response.status_code == 409:
            raise AuthProviderError(status_code=409, detail="Email already registered")

        if response.status_code in {401, 403} and context in {"service_account", "create_user"}:
            raise AuthProviderError(
                status_code=502,
                detail="Identity provider rejected FortiDashboard service account",
                audit_outcome="provider_configuration_error",
            )

        if response.status_code >= 500:
            raise AuthProviderError(
                status_code=503,
                detail="Identity provider unavailable",
                audit_outcome="provider_unavailable",
            )

        raise AuthProviderError(
            status_code=502,
            detail="Identity provider rejected authentication request",
            audit_outcome="provider_error",
        )

    def _realm_url(self, path: str) -> str:
        return urljoin(self.base_url, f"realms/{self.realm}/{path}")

    def _admin_url(self, path: str) -> str:
        return urljoin(self.base_url, f"admin/realms/{self.realm}/{path}")
