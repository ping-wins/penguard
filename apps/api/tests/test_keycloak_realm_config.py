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
