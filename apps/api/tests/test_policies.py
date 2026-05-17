from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.auth.permissions import VALID_PERMISSION_SLUGS
from app.main import app
from app.policies.fortigate_adapter import FortiGatePolicyAdapter
from app.policies.models import PolicyReviewApplyRequest, PolicyReviewCreateRequest
from app.routers import policies as policies_router

client = TestClient(app)


def test_policy_manager_permission_is_registered() -> None:
    assert "policies.manage" in VALID_PERMISSION_SLUGS


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


class FakePolicyService:
    def list_providers(self, *, owner_user_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        return {
            "items": [
                {
                    "providerType": "fortigate",
                    "integrationId": "int_fgt_01",
                    "name": "FortiGate Lab",
                    "capabilities": ["list", "create", "edit", "enable", "disable", "delete"],
                    "policyKinds": ["firewall_policy", "lab_allow_log", "temporary_block"],
                }
            ]
        }

    def list_policies(self, *, owner_user_id: str, filters: dict) -> dict:
        assert owner_user_id == "usr_admin"
        assert filters["providerType"] == "fortigate"
        return {
            "items": [
                {
                    "id": "fortigate:int_fgt_01:policy:10",
                    "providerType": "fortigate",
                    "integrationId": "int_fgt_01",
                    "nativeId": "10",
                    "name": "LAN to WAN",
                    "kind": "firewall_policy",
                    "status": "enabled",
                    "action": "accept",
                    "direction": {"source": "port2", "destination": "port3"},
                    "scope": {
                        "source": ["LAN_NET"],
                        "destination": ["WAN_NET"],
                        "service": ["HTTPS"],
                    },
                    "ownership": "external",
                    "managedByFortiDashboard": False,
                    "isMutable": True,
                    "supports": ["edit", "disable", "delete"],
                    "risk": {"level": "medium", "reasons": ["Allows traffic"]},
                    "summary": "accept HTTPS from LAN_NET to WAN_NET",
                    "lastObservedAt": "2026-05-17T12:00:00.000Z",
                }
            ],
            "nextCursor": None,
        }

    def create_review(self, *, owner_user_id: str, payload):
        assert owner_user_id == "usr_admin"
        return {
            "id": "policy_review_01",
            "providerType": payload.provider_type,
            "integrationId": payload.integration_id,
            "policyId": payload.policy_id,
            "action": payload.action,
            "status": "pending_review",
            "title": "Disable LAN to WAN",
            "before": {"summary": "enabled"},
            "after": {"summary": "disabled"},
            "diff": [
                {
                    "field": "status",
                    "before": "enabled",
                    "after": "disabled",
                    "risk": "Stops traffic",
                }
            ],
            "warnings": [{"severity": "high", "message": "External policy"}],
            "rollback": ["Set status back to enabled"],
            "reviewHash": "hash_01",
        }

    def apply_review(self, *, owner_user_id: str, review_id: str, payload):
        assert owner_user_id == "usr_admin"
        assert review_id == "policy_review_01"
        assert payload.confirmed is True
        return {
            "id": "policy_review_01",
            "status": "applied",
            "providerType": "fortigate",
            "integrationId": "int_fgt_01",
            "appliedResult": {"ok": True},
        }


def _admin_user() -> dict:
    return {
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }


def test_policy_manager_lists_providers_and_inventory() -> None:
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[policies_router.get_policy_service] = lambda: FakePolicyService()
    try:
        providers = client.get("/api/policies/providers")
        inventory = client.get("/api/policies", params={"providerType": "fortigate"})
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(policies_router.get_policy_service, None)

    assert providers.status_code == 200
    assert providers.json()["items"][0]["providerType"] == "fortigate"
    assert inventory.status_code == 200
    assert inventory.json()["items"][0]["name"] == "LAN to WAN"


def test_policy_manager_review_and_apply_require_admin_confirmation() -> None:
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[policies_router.get_policy_service] = lambda: FakePolicyService()
    try:
        review = client.post(
            "/api/policies/reviews",
            headers=csrf_headers(),
            json={
                "providerType": "fortigate",
                "integrationId": "int_fgt_01",
                "policyId": "fortigate:int_fgt_01:policy:10",
                "action": "disable",
                "payload": {},
            },
        )
        applied = client.post(
            "/api/policies/reviews/policy_review_01/apply",
            headers=csrf_headers(),
            json={"reviewHash": "hash_01", "confirmed": True},
        )
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(policies_router.get_policy_service, None)

    assert review.status_code == 201
    assert review.json()["status"] == "pending_review"
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"


class FakeFortiGatePolicyClient:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    def get_policies(self) -> list[dict]:
        return [
            {
                "policyid": 10,
                "name": "LAN to WAN",
                "status": "enable",
                "action": "accept",
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "LAN_NET"}],
                "dstaddr": [{"name": "WAN_NET"}],
                "service": [{"name": "HTTPS"}],
            }
        ]

    def update_firewall_policy(self, policy_id: str, payload: dict) -> dict:
        self.updated.append((policy_id, payload))
        return {"updated": policy_id}

    def delete_firewall_policy(self, policy_id: str) -> dict:
        self.deleted.append(policy_id)
        return {"deleted": policy_id}


class FakeFortiGatePolicyService:
    def __init__(self, client: FakeFortiGatePolicyClient) -> None:
        self.client = client

    def list(self, *, owner_user_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        return {"items": [{"id": "int_fgt_01", "name": "FortiGate Lab"}]}

    def client_for_integration(self, integration_id: str, *, owner_user_id: str):
        assert integration_id == "int_fgt_01"
        assert owner_user_id == "usr_admin"
        return self.client


def test_fortigate_policy_adapter_normalizes_inventory() -> None:
    adapter = FortiGatePolicyAdapter(FakeFortiGatePolicyService(FakeFortiGatePolicyClient()))

    result = adapter.list_policies(owner_user_id="usr_admin", filters={})
    row = result.items[0].model_dump(mode="json", by_alias=True)

    assert row["id"] == "fortigate:int_fgt_01:policy:10"
    assert row["providerType"] == "fortigate"
    assert row["ownership"] == "external"
    assert row["managedByFortiDashboard"] is False
    assert row["supports"] == ["edit", "disable", "delete"]
    assert row["scope"]["service"] == ["HTTPS"]


def test_fortigate_policy_adapter_creates_disable_review_and_apply() -> None:
    client = FakeFortiGatePolicyClient()
    adapter = FortiGatePolicyAdapter(FakeFortiGatePolicyService(client))

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortigate",
            integrationId="int_fgt_01",
            policyId="fortigate:int_fgt_01:policy:10",
            action="disable",
            payload={},
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert review.status == "pending_review"
    assert review.diff[0]["field"] == "status"
    assert client.updated == [("10", {"status": "disable"})]
    assert applied["status"] == "applied"
    assert applied["appliedResult"] == {"updated": "10"}
