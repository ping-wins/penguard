import httpx
import pytest

from app.integrations.fortiweb.client import FortiWebApiClient, FortiWebApiError


def test_fortiweb_client_uses_supported_system_status_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2.0/system/status"
        assert request.headers["authorization"] == "fortiweb-auth"
        return httpx.Response(
            200,
            content=b"{ cpu: 30 memory: 30 }",
            headers={"Content-Type": "application/json"},
        )

    client = FortiWebApiClient(
        host="https://fortiweb.local/",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_system_status() == {"cpu": 30, "memory": 30}


def test_fortiweb_client_rejects_unparseable_status_payload() -> None:
    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                content=b"not a status payload",
                headers={"Content-Type": "application/json"},
            )
        ),
    )

    with pytest.raises(FortiWebApiError, match="non-JSON response"):
        client.get_system_status()
