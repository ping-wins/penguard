import pytest

from app.integrations.connect_persistence import (
    UnsupportedProviderType,
    persist_integration,
    validate_auth,
)


def test_validate_auth_missing_required_field_raises() -> None:
    fields = [{"id": "host", "label": "URL", "type": "url", "required": True}]
    with pytest.raises(ValueError) as exc:
        validate_auth(fields, {})
    assert "host" in str(exc.value)


def test_validate_auth_applies_defaults() -> None:
    fields = [
        {"id": "host", "label": "URL", "type": "url", "required": True},
        {"id": "verifyTls", "label": "Verify", "type": "boolean", "default": False},
    ]
    cleaned = validate_auth(fields, {"host": "https://x"})
    assert cleaned == {"host": "https://x", "verifyTls": False}


def test_persist_fortigate_routes_to_legacy_service() -> None:
    service = _FakeVendorService("fortigate-1")
    result = persist_integration(
        provider_type="fortigate",
        owner_user_id="u1",
        name="Gate",
        auth={"host": "https://fg", "apiKey": "k", "verifyTls": True},
        device={},
        services={"fortigate": service},
    )
    assert result == {"id": "fortigate-1"}
    assert service.calls == [
        {
            "owner_user_id": "u1",
            "name": "Gate",
            "host": "https://fg",
            "api_key": "k",
            "verify_tls": True,
        }
    ]


def test_persist_fortiweb_routes_to_legacy_service() -> None:
    service = _FakeVendorService("fortiweb-1")
    result = persist_integration(
        provider_type="fortiweb",
        owner_user_id="u1",
        name="WAF",
        auth={"host": "https://fw", "apiKey": "k"},
        device={},
        services={"fortiweb": service},
    )
    assert result == {"id": "fortiweb-1"}
    assert service.calls[0]["verify_tls"] is False


def test_persist_penguin_routes_to_legacy_service() -> None:
    service = _FakePenguinService()
    result = persist_integration(
        provider_type="soar_skipper",
        owner_user_id="u1",
        name="Skipper",
        auth={"host": "http://soar"},
        device={},
        services={"penguin": service},
    )
    assert result == {"id": "penguin-1"}
    assert service.calls == [
        {"owner_user_id": "u1", "tool_type": "soar_skipper", "name": "Skipper"}
    ]


def test_persist_unknown_provider_type_raises() -> None:
    with pytest.raises(UnsupportedProviderType):
        persist_integration(
            provider_type="totally-unknown",
            owner_user_id="u1",
            name="n",
            auth={},
            device={},
            services={},
        )


class _FakeVendorService:
    def __init__(self, result_id: str) -> None:
        self.result_id = result_id
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": self.result_id}


class _FakePenguinService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "penguin-1"}
