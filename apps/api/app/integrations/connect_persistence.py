from typing import Any

from app.integrations.fortiweb.auth import fortiweb_runtime_auth


class UnsupportedProviderType(ValueError):
    pass


def validate_auth(
    auth_fields: list[dict[str, Any]],
    submitted: dict[str, Any],
) -> dict[str, Any]:
    """Validate submitted auth against manifest fields and apply defaults."""
    cleaned: dict[str, Any] = {}
    for field in auth_fields:
        field_id = str(field["id"])
        if field_id in submitted and submitted[field_id] not in (None, ""):
            cleaned[field_id] = submitted[field_id]
        elif "default" in field and field["default"] is not None:
            cleaned[field_id] = field["default"]
        elif field.get("required"):
            raise ValueError(f"Missing required field: {field_id}")
    return cleaned


def persist_integration(
    *,
    provider_type: str,
    owner_user_id: str,
    name: str,
    auth: dict[str, Any],
    device: dict[str, Any],
    services: dict[str, Any],
) -> dict[str, Any]:
    """Persist via the existing per-provider services.

    A unified integrations table is intentionally deferred; Phase 2 reuses the
    legacy service/store boundaries while the wizard becomes add-on-driven.
    """
    _ = device
    if provider_type == "fortigate":
        return services["fortigate"].create(
            owner_user_id=owner_user_id,
            name=name,
            host=str(auth["host"]),
            api_key=str(auth["apiKey"]),
            verify_tls=bool(auth.get("verifyTls", False)),
        )
    if provider_type == "fortiweb":
        runtime_auth = fortiweb_runtime_auth(auth)
        return services["fortiweb"].create(
            owner_user_id=owner_user_id,
            name=name,
            host=str(runtime_auth["host"]),
            api_key=str(runtime_auth["apiKey"]),
            verify_tls=bool(runtime_auth.get("verifyTls", False)),
            target_server_policy=str(
                runtime_auth.get("targetServerPolicy") or "lab-waf-policy"
            ),
            managed_ip_list_policy=str(
                runtime_auth.get("managedIpListPolicy") or "PG_IP_BLOCKLIST"
            ),
        )
    if provider_type in ("siem_kowalski", "xdr_rico", "soar_skipper"):
        return services["penguin"].create(
            owner_user_id=owner_user_id,
            tool_type=provider_type,
            name=name,
            host=str(auth.get("host") or "").strip(),
        )
    raise UnsupportedProviderType(f"No persistence for provider type: {provider_type}")
