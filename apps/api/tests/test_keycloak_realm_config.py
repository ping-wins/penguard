import json
from pathlib import Path


def test_bff_service_account_can_create_users_in_dev_realm():
    realm = json.loads(Path("../../infra/keycloak/realm-fortidashboard.json").read_text())

    service_account = next(
        (
            user
            for user in realm["users"]
            if user.get("serviceAccountClientId") == "fortidashboard-bff"
        ),
        None,
    )

    assert service_account is not None
    assert set(service_account["clientRoles"]["realm-management"]) >= {
        "manage-users",
        "view-users",
    }


def test_dev_realm_seeds_admin_user_for_audit_poc():
    realm = json.loads(Path("../../infra/keycloak/realm-fortidashboard.json").read_text())

    admin_user = next(
        (
            user
            for user in realm["users"]
            if user.get("username") == "admin@example.com"
        ),
        None,
    )

    assert admin_user is not None
    assert admin_user["email"] == "admin@example.com"
    assert admin_user["enabled"] is True
    assert admin_user["emailVerified"] is True
    assert admin_user["realmRoles"] == ["admin"]
    assert admin_user["credentials"] == [
        {
            "type": "password",
            "value": "correct-horse-battery-staple",
            "temporary": False,
        }
    ]
