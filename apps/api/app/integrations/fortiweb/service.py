from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any, Protocol

from app.integrations.fortiweb.client import FortiWebApiClient, FortiWebApiError
from app.integrations.fortiweb.store import FORTIWEB_CAPABILITIES

PENGUARD_WAF_DOS_INLINE_PROFILE = "Penguard Inline DoS Protection"


class FortiWebIntegrationStore(Protocol):
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        target_server_policy: str,
        managed_ip_list_policy: str,
        telemetry_token_hash: str | None = None,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pass

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        pass

    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        pass

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        pass

    def record_health_check(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        ok: bool,
        status: str,
        device: dict[str, Any],
        message: str | None,
        latency_ms: int | None,
        checked_at: datetime,
    ) -> dict[str, Any]:
        pass

    def get_telemetry_token_hash(self, integration_id: str) -> str | None:
        pass

    def rotate_telemetry_token(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        telemetry_token_hash: str,
    ) -> dict[str, Any]:
        pass

    def record_telemetry_event(
        self,
        *,
        integration_id: str,
        event_id: str | None,
        event_type: str,
        occurred_at: datetime,
    ) -> dict[str, Any]:
        pass

    def create_block_request(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        source_ip: str,
        incident_id: str | None,
        reason: str | None,
        intent: dict[str, Any],
        preflight_summary: dict[str, Any],
        proposed_changes: list[dict[str, Any]],
        review_hash: str,
    ) -> dict[str, Any]:
        pass

    def get_block_request(self, block_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        pass

    def list_blocks(self, *, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        pass

    def mark_block_applied(
        self,
        *,
        block_id: str,
        owner_user_id: str,
        applied_result: dict[str, Any],
    ) -> dict[str, Any]:
        pass

    def mark_block_removed(
        self,
        *,
        block_id: str,
        owner_user_id: str,
        removed_result: dict[str, Any],
    ) -> dict[str, Any]:
        pass


class FortiWebClient(Protocol):
    def get_system_status(self) -> dict[str, Any]:
        pass

    def get_server_policy(self, name: str) -> dict[str, Any]:
        pass

    def update_server_policy(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        pass

    def get_inline_protection_profile(self, name: str) -> dict[str, Any]:
        pass

    def update_inline_protection_profile(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        pass

    def create_inline_protection_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        pass

    def get_application_layer_dos_prevention(self, name: str) -> dict[str, Any]:
        pass

    def get_ip_list(self, name: str) -> dict[str, Any]:
        pass

    def create_ip_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        pass

    def update_ip_list(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        pass


class FortiWebClientFactory(Protocol):
    def __call__(self, *, host: str, api_key: str, verify_tls: bool) -> FortiWebClient:
        pass


class FortiWebConnectionFailed(RuntimeError):
    pass


class MockFortiWebIntegrationService:
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        target_server_policy: str = "lab-waf-policy",
        managed_ip_list_policy: str = "PG_IP_BLOCKLIST",
    ) -> dict[str, Any]:
        _ = (owner_user_id, host, api_key, verify_tls)
        return {
            "id": "int_fweb_01",
            "type": "fortiweb",
            "name": name,
            "status": "connected",
            "capabilities": FORTIWEB_CAPABILITIES,
            "targetServerPolicy": target_server_policy,
            "managedIpListPolicy": managed_ip_list_policy,
            "lastCheckedAt": "2026-05-17T12:00:00.000Z",
            "telemetry": {
                "status": "pending",
                "endpointPath": "/api/soc/ingest/fortiweb/int_fweb_01",
                "token": "fweb_native_token_01",
                "lastEventAt": None,
                "lastError": None,
                "eventsReceived": 0,
            },
        }

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        _ = (host, api_key, verify_tls)
        return {
            "ok": True,
            "status": "connected",
            "device": {
                "hostname": "FWB-VM",
                "model": "FortiWeb-VM",
                "version": "v8.0.x",
                "serial": "FWBVMTEST",
            },
        }

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        _ = owner_user_id
        return {"items": []}

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        _ = owner_user_id
        return integration_id == "int_fweb_01"

    def verify_telemetry_token(self, *, integration_id: str, token: str) -> bool:
        _ = token
        return integration_id == "int_fweb_01"

    def rotate_telemetry_token(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        _ = owner_user_id
        if integration_id != "int_fweb_01":
            raise KeyError("Integration not found")
        return {
            "integrationId": integration_id,
            "telemetry": {
                "status": "pending",
                "endpointPath": f"/api/soc/ingest/fortiweb/{integration_id}",
                "token": "fweb_native_token_02",
                "lastEventAt": None,
                "lastError": None,
                "eventsReceived": 0,
            },
        }

    def record_telemetry_event(
        self,
        *,
        integration_id: str,
        event_id: str | None,
        event_type: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        _ = (event_id, event_type, occurred_at)
        return {
            "integrationId": integration_id,
            "telemetry": {
                "status": "active",
                "endpointPath": f"/api/soc/ingest/fortiweb/{integration_id}",
                "token": None,
                "lastEventAt": "2026-05-17T12:00:00.000Z",
                "lastError": None,
                "eventsReceived": 1,
            },
        }

    def run_health_check(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        _ = owner_user_id
        return {
            "id": "fweb_health_01",
            "integrationId": integration_id,
            "ok": True,
            "status": "connected",
            "device": self.test_connection(
                host="https://fortiweb.local",
                api_key="mock",
                verify_tls=False,
            )["device"],
            "message": None,
            "latencyMs": 0,
            "checkedAt": "2026-05-17T12:00:00.000Z",
        }

    def review_source_block(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        source_ip: str,
        incident_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        _ = owner_user_id
        normalized_ip = _normalize_ip(source_ip)
        intent = {
            "action": "block_source_ip",
            "sourceIp": normalized_ip,
            "incidentId": incident_id,
            "targetServerPolicy": "lab-waf-policy",
            "managedIpListPolicy": "PG_IP_BLOCKLIST",
            "reason": reason,
        }
        preflight_summary = {
            "integrationId": integration_id,
            "serverPolicy": "lab-waf-policy",
            "inlineProtectionProfile": "lab-inline-protection",
            "managedIpListPolicy": "PG_IP_BLOCKLIST",
            "ipListAttached": True,
            "ipListExists": True,
            "alreadyBlocked": False,
        }
        proposed_changes = [_update_ip_list_change("PG_IP_BLOCKLIST", normalized_ip)]
        review_hash = _review_hash(intent, preflight_summary, proposed_changes)
        return {
            "id": "fweb_block_01",
            "integrationId": integration_id,
            "sourceIp": normalized_ip,
            "incidentId": incident_id,
            "status": "pending_review",
            "reason": reason,
            "intent": intent,
            "preflightSummary": preflight_summary,
            "proposedChanges": proposed_changes,
            "reviewHash": review_hash,
            "createdAt": "2026-05-17T12:00:00.000Z",
            "updatedAt": "2026-05-17T12:00:00.000Z",
        }

    def apply_source_block(
        self,
        *,
        owner_user_id: str,
        block_id: str,
        review_hash: str,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        _ = owner_user_id
        if not confirmed:
            raise PermissionError("Explicit confirmation is required to apply FortiWeb block")
        return {
            "id": block_id,
            "integrationId": "int_fweb_01",
            "sourceIp": "10.10.10.10",
            "status": "active",
            "reviewHash": review_hash,
            "appliedResult": {"applied": True},
        }

    def list_blocks(self, *, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        _ = (owner_user_id, integration_id)
        return {"items": []}

    def remove_source_block(self, *, owner_user_id: str, block_id: str) -> dict[str, Any]:
        _ = owner_user_id
        return {
            "id": block_id,
            "integrationId": "int_fweb_01",
            "sourceIp": "10.10.10.10",
            "status": "removed",
            "removedResult": {"removed": True},
        }


class FortiWebIntegrationService:
    def __init__(
        self,
        *,
        store: FortiWebIntegrationStore,
        client_factory: FortiWebClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory or self._default_client_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        target_server_policy: str = "lab-waf-policy",
        managed_ip_list_policy: str = "PG_IP_BLOCKLIST",
    ) -> dict[str, Any]:
        telemetry_token = _generate_telemetry_token()
        probe = self._probe_connection(host=host, api_key=api_key, verify_tls=verify_tls)
        if not probe["ok"]:
            error = probe.get("error") or {}
            raise FortiWebConnectionFailed(error.get("message") or "FortiWeb connection failed")
        created = self.store.create(
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            api_key=api_key,
            verify_tls=verify_tls,
            target_server_policy=target_server_policy,
            managed_ip_list_policy=managed_ip_list_policy,
            telemetry_token_hash=_telemetry_token_hash(telemetry_token),
            device=dict(probe.get("device") or {}),
        )
        return _with_one_time_telemetry_token(created, telemetry_token)

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return self._probe_connection(host=host, api_key=api_key, verify_tls=verify_tls)

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        return self.store.list_public(owner_user_id=owner_user_id)

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        return self.store.delete(owner_user_id=owner_user_id, integration_id=integration_id)

    def verify_telemetry_token(self, *, integration_id: str, token: str) -> bool:
        expected = self.store.get_telemetry_token_hash(integration_id)
        if not expected:
            return False
        return hmac.compare_digest(expected, _telemetry_token_hash(token))

    def rotate_telemetry_token(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        telemetry_token = _generate_telemetry_token()
        rotated = self.store.rotate_telemetry_token(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            telemetry_token_hash=_telemetry_token_hash(telemetry_token),
        )
        return _with_one_time_telemetry_token(rotated, telemetry_token)

    def record_telemetry_event(
        self,
        *,
        integration_id: str,
        event_id: str | None,
        event_type: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        return self.store.record_telemetry_event(
            integration_id=integration_id,
            event_id=event_id,
            event_type=event_type,
            occurred_at=_parse_telemetry_timestamp(occurred_at),
        )

    def run_health_check(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(integration_id, owner_user_id=owner_user_id)
        if connection is None:
            raise KeyError("Integration not found")
        started_at = self.clock()
        result = self._probe_connection(
            host=str(connection["host"]),
            api_key=str(connection["api_key"]),
            verify_tls=bool(connection["verify_tls"]),
        )
        finished_at = self.clock()
        latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        return self.store.record_health_check(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            ok=bool(result["ok"]),
            status=str(result["status"]),
            device=dict(result.get("device") or {}),
            message=(result.get("error") or {}).get("message"),
            latency_ms=latency_ms,
            checked_at=finished_at,
        )

    def review_source_block(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        source_ip: str,
        incident_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        connection, client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        normalized_ip = _normalize_ip(source_ip)
        target_server_policy = str(connection["target_server_policy"])
        managed_ip_list_policy = str(connection["managed_ip_list_policy"])
        preflight_summary, proposed_changes = self._preflight_source_block(
            client=client,
            integration_id=integration_id,
            target_server_policy=target_server_policy,
            managed_ip_list_policy=managed_ip_list_policy,
            source_ip=normalized_ip,
        )
        intent = {
            "action": "block_source_ip",
            "sourceIp": normalized_ip,
            "incidentId": incident_id,
            "targetServerPolicy": target_server_policy,
            "managedIpListPolicy": managed_ip_list_policy,
            "reason": reason,
        }
        review_hash = _review_hash(intent, preflight_summary, proposed_changes)
        return self.store.create_block_request(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            source_ip=normalized_ip,
            incident_id=incident_id,
            reason=reason,
            intent=intent,
            preflight_summary=preflight_summary,
            proposed_changes=proposed_changes,
            review_hash=review_hash,
        )

    def apply_source_block(
        self,
        *,
        owner_user_id: str,
        block_id: str,
        review_hash: str,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required to apply FortiWeb block")
        block = self.store.get_block_request(block_id, owner_user_id=owner_user_id)
        if block is None:
            raise KeyError("FortiWeb block request not found")
        if block["status"] not in ("pending_review", "active"):
            raise PermissionError("FortiWeb block request is not pending review")
        if block["reviewHash"] != review_hash:
            raise PermissionError("FortiWeb block review hash mismatch")
        integration_id = str(block["integrationId"])
        connection, client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        source_ip = str(block["sourceIp"])
        managed_ip_list_policy = str(block["intent"]["managedIpListPolicy"])
        target_server_policy = str(connection["target_server_policy"])
        profile_name = str(block["preflightSummary"]["inlineProtectionProfile"])
        member = _block_member(source_ip)
        ip_list_exists = bool(block["preflightSummary"].get("ipListExists"))
        current_ip_list = (
            client.get_ip_list(managed_ip_list_policy)
            if ip_list_exists
            else {"name": managed_ip_list_policy, "members": []}
        )
        desired_members = _members_without_source(current_ip_list, source_ip)
        desired_members.append(member)
        desired_ip_list = {
            **current_ip_list,
            "name": managed_ip_list_policy,
            "members": desired_members,
        }
        if ip_list_exists:
            client.update_ip_list(managed_ip_list_policy, desired_ip_list)
        else:
            client.create_ip_list(desired_ip_list)
        if not block["preflightSummary"].get("ipListAttached"):
            profile = client.get_inline_protection_profile(profile_name)
            profile["ip-list-policy"] = managed_ip_list_policy
            client.update_inline_protection_profile(profile_name, profile)
        applied_result = {
            "applied": True,
            "sourceIp": source_ip,
            "targetServerPolicy": target_server_policy,
            "managedIpListPolicy": managed_ip_list_policy,
            "mode": "manual_removal_required",
        }
        return self.store.mark_block_applied(
            block_id=block_id,
            owner_user_id=owner_user_id,
            applied_result=applied_result,
        )

    def list_blocks(self, *, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        return self.store.list_blocks(owner_user_id=owner_user_id, integration_id=integration_id)

    def remove_source_block(self, *, owner_user_id: str, block_id: str) -> dict[str, Any]:
        block = self.store.get_block_request(block_id, owner_user_id=owner_user_id)
        if block is None:
            raise KeyError("FortiWeb block request not found")
        if block["status"] != "active":
            raise PermissionError("Only active FortiWeb blocks can be removed")
        integration_id = str(block["integrationId"])
        _, client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        source_ip = str(block["sourceIp"])
        managed_ip_list_policy = str(block["intent"]["managedIpListPolicy"])
        current_ip_list = client.get_ip_list(managed_ip_list_policy)
        desired_ip_list = {
            **current_ip_list,
            "members": _members_without_source(current_ip_list, source_ip),
        }
        client.update_ip_list(managed_ip_list_policy, desired_ip_list)
        removed_result = {
            "removed": True,
            "sourceIp": source_ip,
            "managedIpListPolicy": managed_ip_list_policy,
        }
        return self.store.mark_block_removed(
            block_id=block_id,
            owner_user_id=owner_user_id,
            removed_result=removed_result,
        )

    def review_waf_dos_policy(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        target_server_policy: str | None = None,
        inline_protection_profile: str = PENGUARD_WAF_DOS_INLINE_PROFILE,
        dos_prevention_policy: str = "Predefined",
        reason: str | None = None,
    ) -> dict[str, Any]:
        connection, client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        target_policy = (target_server_policy or str(connection["target_server_policy"])).strip()
        inline_profile = inline_protection_profile.strip()
        dos_policy = dos_prevention_policy.strip()
        if not target_policy:
            raise ValueError("targetServerPolicy is required")
        if not inline_profile:
            raise ValueError("inlineProtectionProfile is required")
        if not dos_policy:
            raise ValueError("dosPreventionPolicy is required")

        server_policy = client.get_server_policy(target_policy)
        profile_exists = True
        try:
            desired_profile = client.get_inline_protection_profile(inline_profile)
        except FortiWebApiError as exc:
            if not _is_fortiweb_not_found_error(exc):
                raise
            desired_profile = {}
            profile_exists = False
        client.get_application_layer_dos_prevention(dos_policy)

        current_profile = _inline_profile_name(server_policy)
        current_traffic_log = _server_policy_traffic_log(server_policy)
        current_dos_policy = _profile_dos_policy(desired_profile)
        preflight_summary = {
            "integrationId": integration_id,
            "serverPolicy": target_policy,
            "currentInlineProtectionProfile": current_profile,
            "desiredInlineProtectionProfile": inline_profile,
            "desiredInlineProtectionProfileExists": profile_exists,
            "currentDosPreventionPolicy": current_dos_policy,
            "desiredDosPreventionPolicy": dos_policy,
            "currentTrafficLog": current_traffic_log,
            "desiredTrafficLog": "enable",
        }
        proposed_changes = _waf_dos_policy_changes(
            target_policy=target_policy,
            current_profile=current_profile,
            inline_profile=inline_profile,
            inline_profile_exists=profile_exists,
            current_dos_policy=current_dos_policy,
            dos_policy=dos_policy,
            current_traffic_log=current_traffic_log,
        )
        intent = {
            "action": "prepare_waf_dos_policy",
            "targetServerPolicy": target_policy,
            "inlineProtectionProfile": inline_profile,
            "dosPreventionPolicy": dos_policy,
            "reason": reason,
        }
        review_hash = _review_hash(intent, preflight_summary, proposed_changes)
        return {
            "id": f"fweb_waf_dos_{review_hash[:12]}",
            "integrationId": integration_id,
            "status": "pending_review",
            "intent": intent,
            "preflightSummary": preflight_summary,
            "proposedChanges": proposed_changes,
            "reviewHash": review_hash,
        }

    def apply_waf_dos_policy(
        self,
        *,
        owner_user_id: str,
        review: dict[str, Any],
        review_hash: str,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError(
                "Explicit confirmation is required to prepare FortiWeb WAF/DoS policy"
            )
        if review.get("reviewHash") != review_hash:
            raise PermissionError("FortiWeb WAF/DoS policy review hash mismatch")
        integration_id = str(review["integrationId"])
        intent = review.get("intent") if isinstance(review.get("intent"), dict) else {}
        target_policy = str(intent.get("targetServerPolicy") or "").strip()
        inline_profile_name = str(intent.get("inlineProtectionProfile") or "").strip()
        dos_policy = str(intent.get("dosPreventionPolicy") or "").strip()
        if not target_policy or not inline_profile_name or not dos_policy:
            raise ValueError("FortiWeb WAF/DoS review is missing required intent fields")

        _, client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        server_policy = client.get_server_policy(target_policy)
        profile_created = False
        try:
            inline_profile = client.get_inline_protection_profile(inline_profile_name)
        except FortiWebApiError as exc:
            if not _is_fortiweb_not_found_error(exc):
                raise
            inline_profile = client.create_inline_protection_profile(
                _inline_profile_create_payload(
                    name=inline_profile_name,
                    dos_policy=dos_policy,
                )
            )
            profile_created = True
        server_updated = False
        profile_updated = False

        if not profile_created and _profile_dos_policy(inline_profile) != dos_policy:
            if _is_read_only_fortiweb_object(inline_profile):
                raise PermissionError(
                    "FortiWeb inline protection profile is read-only; "
                    "choose a Penguard-owned profile"
                )
            client.update_inline_protection_profile(
                inline_profile_name,
                {"application-layer-dos-prevention": dos_policy},
            )
            profile_updated = True

        server_policy_update: dict[str, Any] = {}
        if _inline_profile_name(server_policy) != inline_profile_name:
            server_policy_update["web-protection-profile"] = inline_profile_name
        if _server_policy_traffic_log(server_policy) != "enable":
            server_policy_update["tlog"] = "enable"
        if server_policy_update:
            client.update_server_policy(target_policy, server_policy_update)
            server_updated = True

        return {
            "applied": True,
            "integrationId": integration_id,
            "targetServerPolicy": target_policy,
            "inlineProtectionProfile": inline_profile_name,
            "dosPreventionPolicy": dos_policy,
            "inlineProtectionProfileCreated": profile_created,
            "serverPolicyUpdated": server_updated,
            "trafficLogUpdated": server_policy_update.get("tlog") == "enable",
            "inlineProtectionProfileUpdated": profile_updated,
        }

    def _probe_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        try:
            client = self.client_factory(host=host, api_key=api_key, verify_tls=verify_tls)
            system_status = _normalize_system_status(client.get_system_status())
        except FortiWebApiError as exc:
            return {
                "ok": False,
                "status": "disconnected",
                "error": {"message": str(exc)},
            }
        return {
            "ok": True,
            "status": "connected",
            "device": system_status,
        }

    def _default_client_factory(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> FortiWebClient:
        return FortiWebApiClient(host=host, api_key=api_key, verify_tls=verify_tls)

    def _client_for_integration(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
    ) -> tuple[dict[str, Any], FortiWebClient]:
        connection = self.store.get_connection(integration_id, owner_user_id=owner_user_id)
        if connection is None:
            raise KeyError("Integration not found")
        return connection, self.client_factory(
            host=str(connection["host"]),
            api_key=str(connection["api_key"]),
            verify_tls=bool(connection["verify_tls"]),
        )

    def _preflight_source_block(
        self,
        *,
        client: FortiWebClient,
        integration_id: str,
        target_server_policy: str,
        managed_ip_list_policy: str,
        source_ip: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        server_policy = client.get_server_policy(target_server_policy)
        profile_name = _inline_profile_name(server_policy)
        if not profile_name:
            raise PermissionError(
                "Target FortiWeb server policy must reference a web protection profile"
            )
        profile = client.get_inline_protection_profile(profile_name)
        attached_ip_list = _profile_ip_list_policy(profile)
        if attached_ip_list and attached_ip_list != managed_ip_list_policy:
            raise PermissionError(
                "Target FortiWeb profile already uses a non-Penguard IP list policy"
            )
        ip_list_exists = True
        try:
            ip_list = client.get_ip_list(managed_ip_list_policy)
        except FortiWebApiError as exc:
            if "not found" not in str(exc).lower():
                raise FortiWebConnectionFailed(str(exc)) from exc
            ip_list_exists = False
            ip_list = {"name": managed_ip_list_policy, "members": []}
        members = _ip_list_members(ip_list)
        already_blocked = any(str(member.get("ip")) == source_ip for member in members)
        proposed_changes: list[dict[str, Any]] = []
        if not ip_list_exists:
            proposed_changes.append(
                {
                    "operation": "create_ip_list",
                    "target": managed_ip_list_policy,
                    "summary": (
                        "Create Penguard managed FortiWeb IP list "
                        f"{managed_ip_list_policy}"
                    ),
                }
            )
        if not attached_ip_list:
            proposed_changes.append(
                {
                    "operation": "attach_ip_list_policy",
                    "target": profile_name,
                    "summary": (
                        f"Attach {managed_ip_list_policy} to FortiWeb inline "
                        f"protection profile {profile_name}"
                    ),
                }
            )
        if not already_blocked:
            proposed_changes.append(_update_ip_list_change(managed_ip_list_policy, source_ip))
        return (
            {
                "integrationId": integration_id,
                "serverPolicy": target_server_policy,
                "inlineProtectionProfile": profile_name,
                "managedIpListPolicy": managed_ip_list_policy,
                "ipListAttached": attached_ip_list == managed_ip_list_policy,
                "ipListExists": ip_list_exists,
                "alreadyBlocked": already_blocked,
            },
            proposed_changes,
        )


def _normalize_system_status(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    merged = {**nested, **data, **payload}
    return {
        "hostname": str(
            merged.get("hostname")
            or merged.get("hostName")
            or merged.get("name")
            or "FortiWeb"
        ),
        "model": str(
            merged.get("model")
            or merged.get("model_name")
            or merged.get("platform")
            or "FortiWeb"
        ),
        "version": str(
            merged.get("version")
            or merged.get("firmware")
            or merged.get("firmwareVersion")
            or "unknown"
        ),
        "serial": str(merged.get("serial") or merged.get("serialNumber") or ""),
    }


def _normalize_ip(source_ip: str) -> str:
    return str(ip_address(source_ip))


def _block_member(source_ip: str) -> dict[str, Any]:
    return {
        "ip": source_ip,
        "type": "black-ip",
        "action": "alert_deny",
        "status": "enable",
    }


def _update_ip_list_change(managed_ip_list_policy: str, source_ip: str) -> dict[str, Any]:
    return {
        "operation": "update_ip_list",
        "target": managed_ip_list_policy,
        "summary": f"Add {source_ip} to Penguard managed FortiWeb IP list",
        "sourceIp": source_ip,
        "member": _block_member(source_ip),
    }


def _review_hash(
    intent: dict[str, Any],
    preflight_summary: dict[str, Any],
    proposed_changes: list[dict[str, Any]],
) -> str:
    payload = {
        "intent": intent,
        "preflightSummary": preflight_summary,
        "proposedChanges": proposed_changes,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _generate_telemetry_token() -> str:
    return f"fweb_{secrets.token_urlsafe(32)}"


def _telemetry_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _with_one_time_telemetry_token(payload: dict[str, Any], token: str) -> dict[str, Any]:
    copied = dict(payload)
    telemetry = dict(copied.get("telemetry") or {})
    telemetry["token"] = token
    copied["telemetry"] = telemetry
    return copied


def _parse_telemetry_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _inline_profile_name(server_policy: dict[str, Any]) -> str | None:
    for key in (
        "web-protection-profile",
        "web_protection_profile",
        "webProtectionProfile",
        "inline-protection-profile",
        "profile",
        "profile_name",
    ):
        value = server_policy.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("name") or value.get("q_origin_key")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _profile_ip_list_policy(profile: dict[str, Any]) -> str | None:
    for key in ("ip-list-policy", "ip_list_policy", "ipListPolicy"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("name") or value.get("q_origin_key")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _profile_dos_policy(profile: dict[str, Any]) -> str | None:
    for key in (
        "application-layer-dos-prevention",
        "application_layer_dos_prevention",
        "applicationLayerDosPrevention",
    ):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("name") or value.get("q_origin_key")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _server_policy_traffic_log(server_policy: dict[str, Any]) -> str | None:
    for key in ("tlog", "traffic-log", "traffic_log", "trafficLog"):
        value = server_policy.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
        if isinstance(value, bool):
            return "enable" if value else "disable"
    return None


def _is_fortiweb_not_found_error(error: FortiWebApiError) -> bool:
    return "entry is not found" in str(error).lower()


def _is_read_only_fortiweb_object(payload: dict[str, Any]) -> bool:
    return payload.get("q_type") == 1 and payload.get("can_view") == 1


def _inline_profile_create_payload(*, name: str, dos_policy: str) -> dict[str, Any]:
    return {
        "name": name,
        "client-management": "enable",
        "amf3-protocol-detection": "disable",
        "mobile-app-identification": "",
        "ip-intelligence": "enable",
        "fortigate-quarantined-ips": "disable",
        "quarantined-ip-action": "alert",
        "quarantined-ip-severity": "High",
        "rdt-reason": "disable",
        "jwt-token-location": "token-location-header",
        "application-layer-dos-prevention": dos_policy,
        "comment": "Created by Penguard for WAF/DoS lab validation",
    }


def _waf_dos_policy_changes(
    *,
    target_policy: str,
    current_profile: str | None,
    inline_profile: str,
    inline_profile_exists: bool,
    current_dos_policy: str | None,
    dos_policy: str,
    current_traffic_log: str | None,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if not inline_profile_exists:
        changes.append(
            {
                "operation": "create_inline_protection_profile",
                "target": inline_profile,
                "field": "application-layer-dos-prevention",
                "before": None,
                "after": dos_policy,
                "summary": (
                    f"Create Penguard-owned FortiWeb profile {inline_profile} "
                    f"with {dos_policy} DoS prevention"
                ),
            }
        )
    if current_profile != inline_profile:
        changes.append(
            {
                "operation": "attach_inline_protection_profile",
                "target": target_policy,
                "field": "web-protection-profile",
                "before": current_profile,
                "after": inline_profile,
                "summary": (
                    f"Attach {inline_profile} to FortiWeb server policy "
                    f"{target_policy}"
                ),
            }
        )
    if inline_profile_exists and current_dos_policy != dos_policy:
        changes.append(
            {
                "operation": "attach_dos_prevention_policy",
                "target": inline_profile,
                "field": "application-layer-dos-prevention",
                "before": current_dos_policy,
                "after": dos_policy,
                "summary": f"Attach {dos_policy} DoS prevention to {inline_profile}",
            }
        )
    if current_traffic_log != "enable":
        changes.append(
            {
                "operation": "enable_traffic_log",
                "target": target_policy,
                "field": "tlog",
                "before": current_traffic_log,
                "after": "enable",
                "summary": f"Enable FortiWeb traffic logging on {target_policy}",
            }
        )
    return changes


def _ip_list_members(ip_list: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("members", "member", "entries", "black-ip-list"):
        value = ip_list.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _members_without_source(ip_list: dict[str, Any], source_ip: str) -> list[dict[str, Any]]:
    return [
        dict(member)
        for member in _ip_list_members(ip_list)
        if str(member.get("ip") or member.get("address") or "") != source_ip
    ]
