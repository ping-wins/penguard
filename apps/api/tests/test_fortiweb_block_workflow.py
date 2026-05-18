from typing import Any

from app.integrations.fortiweb.client import FortiWebApiError
from app.integrations.fortiweb.service import FortiWebIntegrationService


class MemoryFortiWebBlockStore:
    def __init__(self):
        self.connection = {
            "id": "int_fweb_lab",
            "host": "https://fortiweb.local",
            "api_key": "fweb_api_key_from_user",
            "verify_tls": False,
            "target_server_policy": "lab-waf-policy",
            "managed_ip_list_policy": "FD_IP_BLOCKLIST",
        }
        self.requests: dict[str, dict[str, Any]] = {}

    def list_public(self, *, owner_user_id: str):
        _ = owner_user_id
        return {"items": []}

    def create(self, **kwargs):
        _ = kwargs
        raise AssertionError("not used")

    def get_connection(self, integration_id: str, *, owner_user_id: str):
        assert integration_id == "int_fweb_lab"
        assert owner_user_id == "usr_admin"
        return dict(self.connection)

    def delete(self, *, owner_user_id: str, integration_id: str):
        _ = (owner_user_id, integration_id)
        return False

    def record_health_check(self, **kwargs):
        _ = kwargs
        raise AssertionError("not used")

    def create_block_request(self, **kwargs):
        request_id = "fweb_block_01"
        payload = {
            "id": request_id,
            "ownerUserId": kwargs["owner_user_id"],
            "integrationId": kwargs["integration_id"],
            "sourceIp": kwargs["source_ip"],
            "incidentId": kwargs["incident_id"],
            "status": "pending_review",
            "reason": kwargs["reason"],
            "intent": kwargs["intent"],
            "preflightSummary": kwargs["preflight_summary"],
            "proposedChanges": kwargs["proposed_changes"],
            "reviewHash": kwargs["review_hash"],
            "appliedResult": None,
            "removedResult": None,
            "createdAt": "2026-05-17T12:00:00.000Z",
            "updatedAt": "2026-05-17T12:00:00.000Z",
        }
        self.requests[request_id] = payload
        return dict(payload)

    def get_block_request(self, block_id: str, *, owner_user_id: str):
        payload = self.requests.get(block_id)
        if payload is None or payload["ownerUserId"] != owner_user_id:
            return None
        return dict(payload)

    def list_blocks(self, *, owner_user_id: str, integration_id: str):
        return {
            "items": [
                dict(payload)
                for payload in self.requests.values()
                if payload["ownerUserId"] == owner_user_id
                and payload["integrationId"] == integration_id
            ]
        }

    def mark_block_applied(self, *, block_id: str, owner_user_id: str, applied_result: dict):
        payload = self.get_block_request(block_id, owner_user_id=owner_user_id)
        assert payload is not None
        payload["status"] = "active"
        payload["appliedResult"] = applied_result
        self.requests[block_id] = payload
        return dict(payload)

    def mark_block_removed(self, *, block_id: str, owner_user_id: str, removed_result: dict):
        payload = self.get_block_request(block_id, owner_user_id=owner_user_id)
        assert payload is not None
        payload["status"] = "removed"
        payload["removedResult"] = removed_result
        self.requests[block_id] = payload
        return dict(payload)


class FortiWebBlockClient:
    def __init__(self):
        self.server_policy = {
            "name": "lab-waf-policy",
            "web-protection-profile": "lab-inline-protection",
        }
        self.inline_profile = {
            "name": "lab-inline-protection",
            "ip-list-policy": "FD_IP_BLOCKLIST",
        }
        self.standard_inline_profile = {
            "name": "Inline Standard Protection",
            "ip-list-policy": "",
            "application-layer-dos-prevention": "",
            "q_type": 1,
            "can_view": 1,
        }
        self.extra_inline_profiles: dict[str, dict[str, Any]] = {}
        self.dos_prevention = {
            "name": "Predefined",
            "enable-http-session-based-prevention": "enable",
            "enable-layer4-dos-prevention": "enable",
        }
        self.ip_list = {
            "name": "FD_IP_BLOCKLIST",
            "members": [],
        }
        self.server_updates: list[dict[str, Any]] = []
        self.ip_list_updates: list[dict[str, Any]] = []
        self.inline_updates: list[dict[str, Any]] = []

    def get_system_status(self):
        return {
            "hostname": "FWB-VM",
            "model": "FortiWeb-VM",
            "version": "v8.0.x",
            "serial": "FWBVMTEST",
        }

    def get_server_policy(self, name: str):
        assert name == "lab-waf-policy"
        return dict(self.server_policy)

    def get_inline_protection_profile(self, name: str):
        if name == "lab-inline-protection":
            return dict(self.inline_profile)
        if name == "Inline Standard Protection":
            return dict(self.standard_inline_profile)
        if name in self.extra_inline_profiles:
            return dict(self.extra_inline_profiles[name])
        if name == "FD Inline DoS Protection":
            raise FortiWebApiError("The entry is not found.")
        raise AssertionError(f"unexpected profile {name}")

    def update_inline_protection_profile(self, name: str, payload: dict[str, Any]):
        if name == "lab-inline-protection":
            self.inline_profile.update(payload)
        elif name == "Inline Standard Protection":
            self.standard_inline_profile.update(payload)
        elif name in self.extra_inline_profiles:
            self.extra_inline_profiles[name].update(payload)
        else:
            raise AssertionError(f"unexpected profile {name}")
        self.inline_updates.append(dict(payload))
        return self.get_inline_protection_profile(name)

    def create_inline_protection_profile(self, payload: dict[str, Any]):
        name = str(payload["name"])
        self.extra_inline_profiles[name] = dict(payload)
        self.inline_updates.append(dict(payload))
        return dict(payload)

    def get_application_layer_dos_prevention(self, name: str):
        assert name == "Predefined"
        return dict(self.dos_prevention)

    def update_server_policy(self, name: str, payload: dict[str, Any]):
        assert name == "lab-waf-policy"
        self.server_policy.update(payload)
        self.server_updates.append(dict(payload))
        return dict(self.server_policy)

    def get_ip_list(self, name: str):
        assert name == "FD_IP_BLOCKLIST"
        return {
            **self.ip_list,
            "members": [dict(member) for member in self.ip_list["members"]],
        }

    def create_ip_list(self, payload: dict[str, Any]):
        self.ip_list = dict(payload)
        self.ip_list_updates.append(dict(payload))
        return dict(self.ip_list)

    def update_ip_list(self, name: str, payload: dict[str, Any]):
        assert name == "FD_IP_BLOCKLIST"
        self.ip_list.update(payload)
        self.ip_list_updates.append(dict(payload))
        return dict(self.ip_list)


def service_with_client(fake_client: FortiWebBlockClient):
    return FortiWebIntegrationService(
        store=MemoryFortiWebBlockStore(),
        client_factory=lambda **_: fake_client,
    )


def test_review_source_block_prepares_managed_ip_list_change_without_ttl():
    fake_client = FortiWebBlockClient()
    service = service_with_client(fake_client)

    review = service.review_source_block(
        owner_user_id="usr_admin",
        integration_id="int_fweb_lab",
        source_ip="10.10.10.10",
        incident_id="inc_dos_01",
        reason="DoS lab attack source",
    )

    assert review["status"] == "pending_review"
    assert review["sourceIp"] == "10.10.10.10"
    assert review["intent"] == {
        "action": "block_source_ip",
        "sourceIp": "10.10.10.10",
        "incidentId": "inc_dos_01",
        "targetServerPolicy": "lab-waf-policy",
        "managedIpListPolicy": "FD_IP_BLOCKLIST",
        "reason": "DoS lab attack source",
    }
    assert "expiresAt" not in review["intent"]
    assert review["proposedChanges"] == [
        {
            "operation": "update_ip_list",
            "target": "FD_IP_BLOCKLIST",
            "summary": "Add 10.10.10.10 to FortiDashboard managed FortiWeb IP list",
            "sourceIp": "10.10.10.10",
            "member": {
                "ip": "10.10.10.10",
                "type": "black-ip",
                "action": "alert_deny",
                "status": "enable",
            },
        }
    ]
    assert "expiresAt" not in str(review["proposedChanges"])


def test_apply_source_block_adds_black_ip_until_user_removes_it():
    fake_client = FortiWebBlockClient()
    service = service_with_client(fake_client)
    review = service.review_source_block(
        owner_user_id="usr_admin",
        integration_id="int_fweb_lab",
        source_ip="10.10.10.10",
        incident_id="inc_dos_01",
        reason="DoS lab attack source",
    )

    applied = service.apply_source_block(
        owner_user_id="usr_admin",
        block_id=review["id"],
        review_hash=review["reviewHash"],
        confirmed=True,
    )

    assert applied["status"] == "active"
    assert fake_client.ip_list["members"] == [
        {
            "ip": "10.10.10.10",
            "type": "black-ip",
            "action": "alert_deny",
            "status": "enable",
        }
    ]
    assert "expiresAt" not in str(fake_client.ip_list)
    assert "ttl" not in str(fake_client.ip_list).lower()


def test_remove_source_block_removes_ip_member_after_explicit_delete():
    fake_client = FortiWebBlockClient()
    service = service_with_client(fake_client)
    review = service.review_source_block(
        owner_user_id="usr_admin",
        integration_id="int_fweb_lab",
        source_ip="10.10.10.10",
        incident_id="inc_dos_01",
        reason="DoS lab attack source",
    )
    service.apply_source_block(
        owner_user_id="usr_admin",
        block_id=review["id"],
        review_hash=review["reviewHash"],
        confirmed=True,
    )

    removed = service.remove_source_block(
        owner_user_id="usr_admin",
        block_id=review["id"],
    )

    assert removed["status"] == "removed"
    assert fake_client.ip_list["members"] == []


def test_review_waf_dos_policy_prepares_server_policy_and_profile_changes():
    fake_client = FortiWebBlockClient()
    fake_client.server_policy["web-protection-profile"] = ""
    service = service_with_client(fake_client)

    review = service.review_waf_dos_policy(
        owner_user_id="usr_admin",
        integration_id="int_fweb_lab",
        reason="Lab DoS validation",
    )

    assert review["status"] == "pending_review"
    assert review["intent"] == {
        "action": "prepare_waf_dos_policy",
        "targetServerPolicy": "lab-waf-policy",
        "inlineProtectionProfile": "FD Inline DoS Protection",
        "dosPreventionPolicy": "Predefined",
        "reason": "Lab DoS validation",
    }
    assert review["preflightSummary"] == {
        "integrationId": "int_fweb_lab",
        "serverPolicy": "lab-waf-policy",
        "currentInlineProtectionProfile": None,
        "desiredInlineProtectionProfile": "FD Inline DoS Protection",
        "desiredInlineProtectionProfileExists": False,
        "currentDosPreventionPolicy": None,
        "desiredDosPreventionPolicy": "Predefined",
    }
    assert [change["operation"] for change in review["proposedChanges"]] == [
        "create_inline_protection_profile",
        "attach_inline_protection_profile",
    ]


def test_apply_waf_dos_policy_updates_fortiweb_through_confirmed_review():
    fake_client = FortiWebBlockClient()
    fake_client.server_policy["web-protection-profile"] = ""
    service = service_with_client(fake_client)
    review = service.review_waf_dos_policy(
        owner_user_id="usr_admin",
        integration_id="int_fweb_lab",
        reason="Lab DoS validation",
    )

    applied = service.apply_waf_dos_policy(
        owner_user_id="usr_admin",
        review=review,
        review_hash=review["reviewHash"],
        confirmed=True,
    )

    assert applied["applied"] is True
    assert fake_client.server_policy["web-protection-profile"] == "FD Inline DoS Protection"
    assert (
        fake_client.extra_inline_profiles["FD Inline DoS Protection"][
            "application-layer-dos-prevention"
        ]
        == "Predefined"
    )
    assert fake_client.server_updates == [
        {"web-protection-profile": "FD Inline DoS Protection"}
    ]
    assert fake_client.inline_updates == [
        {
            "name": "FD Inline DoS Protection",
            "client-management": "enable",
            "amf3-protocol-detection": "disable",
            "mobile-app-identification": "",
            "ip-intelligence": "enable",
            "fortigate-quarantined-ips": "disable",
            "quarantined-ip-action": "alert",
            "quarantined-ip-severity": "High",
            "rdt-reason": "disable",
            "jwt-token-location": "token-location-header",
            "application-layer-dos-prevention": "Predefined",
            "comment": "Created by FortiDashboard for WAF/DoS lab validation",
        }
    ]
