from __future__ import annotations

import hashlib
import ipaddress
import json
from typing import Any

from app.integrations.fortigate.policy_models import (
    FortiGatePolicyAction,
    FortiGatePolicyIntent,
    FortiGatePolicyObjectChange,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyScope,
)

PG_LAB_PREFIX = "PG_LAB_ALLOW"
PG_TMP_BLOCK_PREFIX = "PG_TMP_BLOCK"
PG_ADDR_PREFIX = "PG_ADDR"
LEGACY_LAB_PREFIX = "FD_LAB_ALLOW"
OWNED_POLICY_PREFIXES = ("PG_", "FD_")
LAB_ALLOW_POLICY_PREFIXES = (PG_LAB_PREFIX, LEGACY_LAB_PREFIX)
POLICY_NAME_DIGEST_LENGTH = 12


def normalize_address_name(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    return f"{PG_ADDR_PREFIX}_{str(address).replace('.', '_').replace(':', '_')}"


def host_subnet(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    if address.version == 4:
        return f"{address} 255.255.255.255"
    return f"{address}/128"


class FortiGatePolicyOrchestrator:
    def __init__(self, client: Any, *, integration_id: str) -> None:
        self.client = client
        self.integration_id = integration_id

    def preflight(
        self,
        request: FortiGatePolicyPreflightRequest,
    ) -> FortiGatePolicyPreflightResponse:
        policies = self.client.get_policies()
        address_objects = self.client.get_address_objects()
        changes = self._build_changes(request, address_objects, policies)
        placement = self._placement(request, policies)
        warnings = self._warnings(request, policies)
        policy_name = self._policy_name(request)
        review_hash = self._review_hash(
            request=request,
            changes=changes,
            placement=placement,
            warnings=warnings,
        )
        return FortiGatePolicyPreflightResponse(
            intent=request.intent,
            scope=request.scope,
            integration_id=self.integration_id,
            existing_policy_count=len(policies),
            owned_policy_count=sum(
                1 for policy in policies if _policy_name_starts_with(policy, OWNED_POLICY_PREFIXES)
            ),
            proposed_policy_name=policy_name,
            placement=placement,
            warnings=warnings,
            changes=changes,
            review_hash=review_hash,
        )

    def apply_changes(self, changes: list[FortiGatePolicyObjectChange]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for change in changes:
            if change.operation == "update":
                if change.object_type != "firewall.policy":
                    raise ValueError(f"Unsupported FortiGate update type: {change.object_type}")
                policy_id = str(change.payload.get("policyid") or "")
                if not policy_id:
                    raise ValueError(f"Missing FortiGate policy id for update {change.name}")
                update_payload = {
                    key: value
                    for key, value in change.payload.items()
                    if key not in {"policyid", "policyId", "mkey", "id", "name"}
                }
                result = self.client.update_firewall_policy(policy_id, update_payload)
                applied.append(
                    {
                        "operation": change.operation,
                        "objectType": change.object_type,
                        "name": change.name,
                        "result": result,
                    }
                )
                continue
            if change.operation == "reuse":
                applied.append(
                    {
                        "operation": "reuse",
                        "objectType": change.object_type,
                        "name": change.name,
                    }
                )
                if change.object_type == "firewall.policy":
                    placement_result = self._move_temporary_block_before_lab_allow(
                        policy_name=change.name,
                        create_result={},
                    )
                    if placement_result:
                        applied.append(placement_result)
                continue
            if change.object_type == "firewall.address":
                result = self.client.create_address_object(
                    name=str(change.payload["name"]),
                    subnet=str(change.payload["subnet"]),
                    comment=str(change.payload["comment"]),
                )
            elif change.object_type == "firewall.policy":
                result = self.client.create_firewall_policy(change.payload)
                placement_result = self._move_temporary_block_before_lab_allow(
                    policy_name=change.name,
                    create_result=result,
                )
            else:
                raise ValueError(f"Unsupported FortiGate object type: {change.object_type}")
            applied.append(
                {
                    "operation": change.operation,
                    "objectType": change.object_type,
                    "name": change.name,
                    "result": result,
                }
            )
            if change.object_type == "firewall.policy" and placement_result:
                applied.append(placement_result)
        return applied

    def _move_temporary_block_before_lab_allow(
        self,
        *,
        policy_name: str,
        create_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not policy_name.startswith(PG_TMP_BLOCK_PREFIX):
            return None

        policies = self.client.get_policies()
        lab_allow_policy_id = _first_policy_id_with_prefixes(
            policies,
            LAB_ALLOW_POLICY_PREFIXES,
        )
        if not lab_allow_policy_id:
            return None

        policy_id = _policy_id_from_create_result(create_result)
        if not policy_id:
            policy_id = _policy_id_by_name(policies, policy_name)
        if not policy_id:
            raise ValueError(
                f"Could not resolve FortiGate policy id for temporary block {policy_name}"
            )

        result = self.client.move_firewall_policy(policy_id, before=lab_allow_policy_id)
        return {
            "operation": "move",
            "objectType": "firewall.policy",
            "name": policy_name,
            "before": lab_allow_policy_id,
            "result": result,
        }

    def _build_changes(
        self,
        request: FortiGatePolicyPreflightRequest,
        address_objects: list[dict[str, Any]],
        policies: list[dict[str, Any]],
    ) -> list[FortiGatePolicyObjectChange]:
        matching_lab_allow = _matching_lab_allow_policy(request, address_objects, policies)
        if matching_lab_allow is not None:
            policy_id = _policy_id(matching_lab_allow)
            return [
                FortiGatePolicyObjectChange(
                    operation="update",
                    object_type="firewall.policy",
                    name=str(matching_lab_allow["name"]),
                    payload=_lab_allow_block_update_payload(
                        request=request,
                        policy_id=policy_id,
                        comments=self._comment(request),
                    ),
                )
            ]

        existing_addresses = {str(item.get("name")) for item in address_objects}
        existing_policy_names = {str(item.get("name")) for item in policies}
        source_name = normalize_address_name(request.source_ip)
        changes = [self._address_change(source_name, request.source_ip, existing_addresses)]

        destination_name: str | None = None
        if request.destination_ip:
            destination_name = normalize_address_name(request.destination_ip)
            changes.append(
                self._address_change(destination_name, request.destination_ip, existing_addresses)
            )

        policy_name = self._policy_name(request)
        policy_operation = "reuse" if policy_name in existing_policy_names else "create"
        changes.append(
            FortiGatePolicyObjectChange(
                operation=policy_operation,
                object_type="firewall.policy",
                name=policy_name,
                payload=self._policy_payload(request, source_name, destination_name),
            )
        )
        return changes

    def _address_change(
        self,
        name: str,
        ip_value: str,
        existing_addresses: set[str],
    ) -> FortiGatePolicyObjectChange:
        operation = "reuse" if name in existing_addresses else "create"
        return FortiGatePolicyObjectChange(
            operation=operation,
            object_type="firewall.address",
            name=name,
            payload={
                "name": name,
                "subnet": host_subnet(ip_value),
                "comment": "Penguard owned policy object",
            },
        )

    def _policy_payload(
        self,
        request: FortiGatePolicyPreflightRequest,
        source_name: str,
        destination_name: str | None,
    ) -> dict[str, Any]:
        action = (
            FortiGatePolicyAction.ACCEPT
            if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG
            else FortiGatePolicyAction.DENY
        )
        return {
            "name": self._policy_name(request),
            "srcintf": [{"name": request.source_interface}],
            "dstintf": [{"name": request.destination_interface}],
            "srcaddr": [{"name": source_name}],
            "dstaddr": [{"name": destination_name or "all"}],
            "action": action.value,
            "schedule": "always",
            "service": [{"name": _service_for_policy(request)}],
            "logtraffic": "all",
            "status": "enable",
            "comments": self._comment(request),
        }

    def _policy_name(self, request: FortiGatePolicyPreflightRequest) -> str:
        prefix = (
            PG_LAB_PREFIX
            if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG
            else PG_TMP_BLOCK_PREFIX
        )
        return f"{prefix}_{_policy_digest(request)}"

    def _placement(
        self,
        request: FortiGatePolicyPreflightRequest,
        policies: list[dict[str, Any]],
    ) -> str:
        if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG:
            return "append as Penguard-owned allow/log policy"
        if any(_policy_name_starts_with(policy, LAB_ALLOW_POLICY_PREFIXES) for policy in policies):
            return "before first Penguard-owned lab allow/log policy"
        return "append as Penguard-owned temporary block policy"

    def _warnings(
        self,
        request: FortiGatePolicyPreflightRequest,
        policies: list[dict[str, Any]],
    ) -> list[str]:
        if request.intent != FortiGatePolicyIntent.TEMPORARY_BLOCK:
            return []
        if not any(
            _policy_name_starts_with(policy, LAB_ALLOW_POLICY_PREFIXES)
            for policy in policies
        ):
            return [
                "No Penguard-owned lab allow/log policy was found; "
                "temporary block will be appended."
            ]
        return []

    def _comment(self, request: FortiGatePolicyPreflightRequest) -> str:
        if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG:
            return "Penguard owned lab allow/log policy"
        return "Penguard owned temporary block policy"

    def _review_hash(
        self,
        *,
        request: FortiGatePolicyPreflightRequest,
        changes: list[FortiGatePolicyObjectChange],
        placement: str,
        warnings: list[str],
    ) -> str:
        payload = {
            "intent": request.intent,
            "scope": request.scope,
            "integrationId": self.integration_id,
            "placement": placement,
            "warnings": warnings,
            "changes": [change.model_dump(mode="json") for change in changes],
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()


def _policy_digest(request: FortiGatePolicyPreflightRequest) -> str:
    payload = {
        "intent": str(request.intent),
        "scope": str(request.scope),
        "sourceInterface": request.source_interface,
        "destinationInterface": request.destination_interface,
        "sourceIp": str(ipaddress.ip_address(request.source_ip)),
        "destinationIp": (
            str(ipaddress.ip_address(request.destination_ip)) if request.destination_ip else ""
        ),
        "service": _service_for_policy(request),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:POLICY_NAME_DIGEST_LENGTH].upper()


def _service_for_policy(request: FortiGatePolicyPreflightRequest) -> str:
    if request.scope == FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE:
        return request.service or "ALL"
    return "ALL"


def _matching_lab_allow_policy(
    request: FortiGatePolicyPreflightRequest,
    address_objects: list[dict[str, Any]],
    policies: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if (
        request.intent != FortiGatePolicyIntent.TEMPORARY_BLOCK
        or not request.destination_ip
    ):
        if request.scope != FortiGatePolicyScope.SOURCE_ONLY:
            return None
    if request.intent != FortiGatePolicyIntent.TEMPORARY_BLOCK:
        return None

    address_subnets = {
        str(item.get("name") or ""): str(item.get("subnet") or "")
        for item in address_objects
        if item.get("name")
    }
    source_subnet = host_subnet(request.source_ip)
    destination_subnet = host_subnet(request.destination_ip) if request.destination_ip else ""
    for policy in policies:
        if not _policy_name_starts_with(policy, LAB_ALLOW_POLICY_PREFIXES):
            continue
        if not _policy_interface_matches(policy, "srcintf", request.source_interface):
            continue
        if not _policy_interface_matches(policy, "dstintf", request.destination_interface):
            continue
        if not _policy_addresses_match(policy, "srcaddr", source_subnet, address_subnets):
            continue
        if (
            request.scope != FortiGatePolicyScope.SOURCE_ONLY
            and not _policy_addresses_match(policy, "dstaddr", destination_subnet, address_subnets)
            and not _policy_has_broader_destination_deny(policy)
        ):
            continue
        if _policy_id(policy):
            return policy
    return None


def _lab_allow_block_update_payload(
    *,
    request: FortiGatePolicyPreflightRequest,
    policy_id: str,
    comments: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "policyid": policy_id,
        "action": FortiGatePolicyAction.DENY.value,
        "service": [{"name": _service_for_policy(request)}],
        "logtraffic": "all",
        "status": "enable",
        "comments": comments,
    }
    if request.scope == FortiGatePolicyScope.SOURCE_ONLY:
        payload["dstaddr"] = [{"name": "all"}]
    return payload


def _policy_interface_matches(policy: dict[str, Any], key: str, expected: str) -> bool:
    return expected in _policy_ref_names(policy, key)


def _policy_addresses_match(
    policy: dict[str, Any],
    key: str,
    expected_subnet: str,
    address_subnets: dict[str, str],
) -> bool:
    return any(
        address_subnets.get(name) == expected_subnet
        for name in _policy_ref_names(policy, key)
    )


def _policy_ref_names(policy: dict[str, Any], key: str) -> list[str]:
    values = policy.get(key)
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for value in values:
        if isinstance(value, dict) and value.get("name"):
            names.append(str(value["name"]))
    return names


def _policy_has_broader_destination_deny(policy: dict[str, Any]) -> bool:
    return str(policy.get("action") or "").lower() == "deny" and "all" in _policy_ref_names(
        policy,
        "dstaddr",
    )


def _first_policy_id_with_prefixes(
    policies: list[dict[str, Any]],
    prefixes: tuple[str, ...],
) -> str:
    for policy in policies:
        if _policy_name_starts_with(policy, prefixes):
            policy_id = _policy_id(policy)
            if policy_id:
                return policy_id
    return ""


def _policy_name_starts_with(policy: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    return str(policy.get("name") or "").startswith(prefixes)


def _policy_id_by_name(policies: list[dict[str, Any]], name: str) -> str:
    for policy in policies:
        if str(policy.get("name") or "") == name:
            policy_id = _policy_id(policy)
            if policy_id:
                return policy_id
    return ""


def _policy_id_from_create_result(result: dict[str, Any]) -> str:
    for key in ("policyid", "policyId", "mkey", "id"):
        policy_id = _policy_id({key: result.get(key)})
        if policy_id:
            return policy_id
    return ""


def _policy_id(policy: dict[str, Any]) -> str:
    for key in ("policyid", "policyId", "mkey", "id"):
        value = policy.get(key)
        if isinstance(value, int) and value >= 0:
            return str(value)
        if isinstance(value, str) and value.isdigit():
            return value
    return ""
