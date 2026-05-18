from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.auth.permissions import VALID_PERMISSION_SLUGS
from app.main import app
from app.policies.fortigate_adapter import FortiGatePolicyAdapter
from app.policies.fortiweb_adapter import FortiWebPolicyAdapter
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
        self.created: list[dict] = []
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

    def create_firewall_policy(self, payload: dict) -> dict:
        self.created.append(payload)
        return {"created": payload.get("name")}

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


def test_fortigate_policy_adapter_creates_firewall_policy() -> None:
    client = FakeFortiGatePolicyClient()
    adapter = FortiGatePolicyAdapter(FakeFortiGatePolicyService(client))

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortigate",
            integrationId="int_fgt_01",
            action="create",
            payload={
                "name": "FD_ALLOW_SOC_TO_WAF",
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "all"}],
                "dstaddr": [{"name": "all"}],
                "service": [{"name": "HTTPS"}],
                "action": "accept",
                "schedule": "always",
                "logtraffic": "all",
                "status": "enable",
            },
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert client.created == [
        {
            "name": "FD_ALLOW_SOC_TO_WAF",
            "srcintf": [{"name": "port2"}],
            "dstintf": [{"name": "port3"}],
            "srcaddr": [{"name": "all"}],
            "dstaddr": [{"name": "all"}],
            "service": [{"name": "HTTPS"}],
            "action": "accept",
            "schedule": "always",
            "logtraffic": "all",
            "status": "enable",
        }
    ]
    assert applied["appliedResult"] == {"created": "FD_ALLOW_SOC_TO_WAF"}


class FakeFortiWebPolicyService:
    def __init__(self) -> None:
        self.applied: list[tuple[str, str, bool]] = []
        self.waf_reviews: list[tuple[str, str, str, str | None]] = []
        self.waf_applied: list[tuple[str, bool]] = []
        self.removed: list[str] = []

    def list(self, *, owner_user_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        return {
            "items": [
                {
                    "id": "int_fweb_01",
                    "type": "fortiweb",
                    "name": "FortiWeb Lab",
                    "status": "connected",
                    "targetServerPolicy": "lab-waf-policy",
                    "managedIpListPolicy": "FD_IP_BLOCKLIST",
                }
            ]
        }

    def list_blocks(self, *, owner_user_id: str, integration_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        assert integration_id == "int_fweb_01"
        return {
            "items": [
                {
                    "id": "fweb_block_01",
                    "integrationId": "int_fweb_01",
                    "sourceIp": "203.0.113.10",
                    "incidentId": "inc_dos_01",
                    "status": "active",
                    "reason": "DoS source",
                    "intent": {
                        "targetServerPolicy": "lab-waf-policy",
                        "managedIpListPolicy": "FD_IP_BLOCKLIST",
                    },
                    "preflightSummary": {
                        "serverPolicy": "lab-waf-policy",
                        "managedIpListPolicy": "FD_IP_BLOCKLIST",
                    },
                    "proposedChanges": [],
                    "reviewHash": "hash_01",
                    "updatedAt": "2026-05-17T12:00:00.000Z",
                }
            ]
        }

    def review_source_block(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        source_ip: str,
        incident_id: str | None = None,
        reason: str | None = None,
    ) -> dict:
        assert owner_user_id == "usr_admin"
        assert integration_id == "int_fweb_01"
        assert source_ip == "203.0.113.10"
        return {
            "id": "fweb_block_02",
            "integrationId": integration_id,
            "sourceIp": source_ip,
            "incidentId": incident_id,
            "status": "pending_review",
            "reason": reason,
            "intent": {
                "targetServerPolicy": "lab-waf-policy",
                "managedIpListPolicy": "FD_IP_BLOCKLIST",
            },
            "preflightSummary": {
                "serverPolicy": "lab-waf-policy",
                "managedIpListPolicy": "FD_IP_BLOCKLIST",
                "alreadyBlocked": False,
            },
            "proposedChanges": [
                {
                    "operation": "update_ip_list",
                    "summary": "Add 203.0.113.10 to FortiDashboard managed FortiWeb IP list",
                }
            ],
            "reviewHash": "fweb_hash_02",
        }

    def apply_source_block(
        self,
        *,
        owner_user_id: str,
        block_id: str,
        review_hash: str,
        confirmed: bool = False,
    ) -> dict:
        assert owner_user_id == "usr_admin"
        self.applied.append((block_id, review_hash, confirmed))
        return {
            "id": block_id,
            "integrationId": "int_fweb_01",
            "sourceIp": "203.0.113.10",
            "status": "active",
            "reviewHash": review_hash,
            "appliedResult": {"applied": True},
        }

    def review_waf_dos_policy(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        target_server_policy: str | None = None,
        inline_protection_profile: str = "FD Inline DoS Protection",
        dos_prevention_policy: str = "Predefined",
        reason: str | None = None,
    ) -> dict:
        assert owner_user_id == "usr_admin"
        assert integration_id == "int_fweb_01"
        self.waf_reviews.append(
            (
                target_server_policy or "lab-waf-policy",
                inline_protection_profile,
                dos_prevention_policy,
                reason,
            )
        )
        return {
            "id": "fortiweb_waf_dos_review_01",
            "integrationId": integration_id,
            "status": "pending_review",
            "intent": {
                "action": "prepare_waf_dos_policy",
                "targetServerPolicy": target_server_policy or "lab-waf-policy",
                "inlineProtectionProfile": inline_protection_profile,
                "dosPreventionPolicy": dos_prevention_policy,
                "reason": reason,
            },
            "preflightSummary": {
                "serverPolicy": "lab-waf-policy",
                "currentInlineProtectionProfile": None,
                "desiredInlineProtectionProfile": inline_protection_profile,
                "desiredInlineProtectionProfileExists": False,
                "currentDosPreventionPolicy": None,
                "desiredDosPreventionPolicy": dos_prevention_policy,
            },
            "proposedChanges": [
                {
                    "operation": "create_inline_protection_profile",
                    "summary": (
                        "Create FortiDashboard-owned FortiWeb profile "
                        f"{inline_protection_profile} with {dos_prevention_policy} DoS prevention"
                    ),
                },
                {
                    "operation": "attach_inline_protection_profile",
                    "summary": (
                        f"Attach {inline_protection_profile} to FortiWeb "
                        "server policy lab-waf-policy"
                    ),
                },
            ],
            "reviewHash": "waf_dos_hash_01",
        }

    def apply_waf_dos_policy(
        self,
        *,
        owner_user_id: str,
        review: dict,
        review_hash: str,
        confirmed: bool = False,
    ) -> dict:
        assert owner_user_id == "usr_admin"
        self.waf_applied.append((review_hash, confirmed))
        return {
            "applied": True,
            "integrationId": "int_fweb_01",
            "targetServerPolicy": review["intent"]["targetServerPolicy"],
            "inlineProtectionProfile": review["intent"]["inlineProtectionProfile"],
            "dosPreventionPolicy": review["intent"]["dosPreventionPolicy"],
        }

    def remove_source_block(self, *, owner_user_id: str, block_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        self.removed.append(block_id)
        return {
            "id": block_id,
            "integrationId": "int_fweb_01",
            "sourceIp": "203.0.113.10",
            "status": "removed",
            "removedResult": {"removed": True},
        }


def test_fortiweb_policy_adapter_lists_configured_policy_and_blocks() -> None:
    adapter = FortiWebPolicyAdapter(FakeFortiWebPolicyService())

    providers = adapter.provider_summary(owner_user_id="usr_admin")
    result = adapter.list_policies(owner_user_id="usr_admin", filters={})
    rows = [row.model_dump(mode="json", by_alias=True) for row in result.items]

    assert providers[0].model_dump(mode="json", by_alias=True) == {
        "providerType": "fortiweb",
        "integrationId": "int_fweb_01",
        "name": "FortiWeb Lab",
        "capabilities": ["list", "create", "edit", "delete"],
        "policyKinds": ["server_policy", "ip_blocklist", "source_block"],
    }
    assert [row["kind"] for row in rows] == ["server_policy", "ip_blocklist", "source_block"]
    assert rows[0]["name"] == "lab-waf-policy"
    assert rows[1]["managedByFortiDashboard"] is True
    assert rows[2]["supports"] == ["delete"]


def test_fortiweb_policy_adapter_creates_source_block_review_and_apply() -> None:
    service = FakeFortiWebPolicyService()
    adapter = FortiWebPolicyAdapter(service)

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortiweb",
            integrationId="int_fweb_01",
            action="create",
            payload={
                "sourceIp": "203.0.113.10",
                "incidentId": "inc_dos_01",
                "reason": "DoS source",
            },
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert review.id == "fortiweb:fweb_block_02"
    assert review.diff[0]["field"] == "update_ip_list"
    assert service.applied == [("fweb_block_02", "fweb_hash_02", True)]
    assert applied["status"] == "applied"
    assert applied["appliedResult"]["appliedResult"] == {"applied": True}


def test_fortiweb_policy_adapter_reviews_and_applies_waf_dos_policy_edit() -> None:
    service = FakeFortiWebPolicyService()
    adapter = FortiWebPolicyAdapter(service)

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortiweb",
            integrationId="int_fweb_01",
            policyId="fortiweb:int_fweb_01:server-policy:lab-waf-policy",
            action="edit",
            payload={
                "operation": "prepare_waf_dos_policy",
                "inlineProtectionProfile": "FD Inline DoS Protection",
                "dosPreventionPolicy": "Predefined",
                "reason": "Lab DoS validation",
            },
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert review.id.startswith("fortiweb:waf-dos:")
    assert review.action == "edit"
    assert [entry["field"] for entry in review.diff] == [
        "create_inline_protection_profile",
        "attach_inline_protection_profile",
    ]
    assert service.waf_reviews == [
        (
            "lab-waf-policy",
            "FD Inline DoS Protection",
            "Predefined",
            "Lab DoS validation",
        )
    ]
    assert service.waf_applied == [("waf_dos_hash_01", True)]
    assert applied["appliedResult"]["applied"] is True


def test_fortiweb_policy_adapter_reviews_and_removes_source_block() -> None:
    service = FakeFortiWebPolicyService()
    adapter = FortiWebPolicyAdapter(service)

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortiweb",
            integrationId="int_fweb_01",
            policyId="fortiweb:int_fweb_01:block:fweb_block_01",
            action="delete",
            payload={},
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert review.action == "delete"
    assert service.removed == ["fweb_block_01"]
    assert applied["appliedResult"]["removedResult"] == {"removed": True}
