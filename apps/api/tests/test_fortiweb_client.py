import json

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


def test_fortiweb_client_accepts_named_resource_wrapped_in_single_result() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path.endswith("/server-policy/policy"):
            assert request.url.params["mkey"] == "lab-waf-policy"
            return httpx.Response(200, json={"results": [{"name": "lab-waf-policy"}]})
        if (
            request.method == "GET"
            and "web-protection-profile.inline-protection" in request.url.path
        ):
            assert request.url.params["mkey"] == "Inline Standard Protection"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Inline Standard Protection",
                            "application-layer-dos-prevention": "",
                        }
                    ]
                },
            )
        if request.method == "GET" and "application-layer-dos-prevention" in request.url.path:
            assert request.url.params["mkey"] == "Predefined"
            return httpx.Response(200, json={"results": [{"name": "Predefined"}]})
        if request.method == "PUT" and request.url.path.endswith("/server-policy/policy"):
            assert request.url.params["mkey"] == "lab-waf-policy"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"data": {"web-protection-profile": "Inline Standard Protection"}}
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "lab-waf-policy",
                            **payload["data"],
                        }
                    ]
                },
            )
        if (
            request.method == "POST"
            and "web-protection-profile.inline-protection" in request.url.path
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {
                "data": {
                    "name": "Penguard Inline DoS Protection",
                    "application-layer-dos-prevention": "Predefined",
                }
            }
            return httpx.Response(200, json={"results": [payload["data"]]})
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_server_policy("lab-waf-policy") == {"name": "lab-waf-policy"}
    assert client.get_inline_protection_profile("Inline Standard Protection")["name"] == (
        "Inline Standard Protection"
    )
    assert client.get_application_layer_dos_prevention("Predefined") == {"name": "Predefined"}
    updated = client.update_server_policy(
        "lab-waf-policy",
        {"web-protection-profile": "Inline Standard Protection"},
    )
    created = client.create_inline_protection_profile(
        {
            "name": "Penguard Inline DoS Protection",
            "application-layer-dos-prevention": "Predefined",
        }
    )

    assert updated["web-protection-profile"] == "Inline Standard Protection"
    assert created["name"] == "Penguard Inline DoS Protection"
    assert any("web-protection-profile.inline-protection" in path for _, path in seen)


def test_fortiweb_client_selects_named_resource_from_collection_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "web-protection-profile.inline-protection" in request.url.path
        assert request.url.params["mkey"] == "Inline Standard Protection"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "API Protection",
                        "application-layer-dos-prevention": "",
                    },
                    {
                        "name": "Inline Standard Protection",
                        "application-layer-dos-prevention": "Predefined",
                    },
                ]
            },
        )

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    profile = client.get_inline_protection_profile("Inline Standard Protection")

    assert profile == {
        "name": "Inline Standard Protection",
        "application-layer-dos-prevention": "Predefined",
    }


def test_fortiweb_client_treats_empty_ip_list_collection_as_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2.0/cmdb/waf/ip-list/PG_IP_BLOCKLIST"
        return httpx.Response(200, json={"results": []})

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FortiWebApiError, match="not found"):
        client.get_ip_list("PG_IP_BLOCKLIST")


def test_fortiweb_client_wraps_ip_list_create_payload() -> None:
    payload = {
        "name": "PG_IP_BLOCKLIST",
        "members": [{"ip": "10.10.10.10", "type": "black-ip"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v2.0/cmdb/waf/ip-list"
        assert json.loads(request.content.decode("utf-8")) == {"data": payload}
        return httpx.Response(200, json={"results": [payload]})

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.create_ip_list(payload) == payload


def test_fortiweb_client_wraps_ip_list_update_payload() -> None:
    payload = {
        "name": "PG_IP_BLOCKLIST",
        "members": [{"ip": "10.10.10.10", "type": "black-ip"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/api/v2.0/cmdb/waf/ip-list/PG_IP_BLOCKLIST"
        assert json.loads(request.content.decode("utf-8")) == {"data": payload}
        return httpx.Response(200, json={"results": [payload]})

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.update_ip_list("PG_IP_BLOCKLIST", payload) == payload


def test_fortiweb_client_creates_ip_list_member_subobject() -> None:
    payload = {
        "id": "1",
        "seq": 1,
        "type": "black-ip",
        "ip": "10.10.10.10",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v2.0/cmdb/waf/ip-list/members"
        assert request.url.params["mkey"] == "PG_IP_BLOCKLIST"
        assert json.loads(request.content.decode("utf-8")) == {"data": payload}
        return httpx.Response(200, json={"results": [payload]})

    client = FortiWebApiClient(
        host="https://fortiweb.local",
        api_key="fortiweb-auth",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.create_ip_list_member("PG_IP_BLOCKLIST", payload) == payload
