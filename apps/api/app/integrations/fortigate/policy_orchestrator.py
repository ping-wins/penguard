from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any

from app.integrations.fortigate.policy_models import (
    FortiGatePolicyAction,
    FortiGatePolicyIntent,
    FortiGatePolicyObjectChange,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyScope,
)

FD_LAB_PREFIX = "FD_LAB_ALLOW"
FD_TMP_BLOCK_PREFIX = "FD_TMP_BLOCK"
FD_ADDR_PREFIX = "FD_ADDR"


def normalize_address_name(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    return f"{FD_ADDR_PREFIX}_{str(address).replace('.', '_').replace(':', '_')}"


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
        changes = self._build_changes(request, address_objects)
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
                1 for policy in policies if str(policy.get("name") or "").startswith("FD_")
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
            if change.operation == "reuse":
                applied.append(
                    {
                        "operation": "reuse",
                        "objectType": change.object_type,
                        "name": change.name,
                    }
                )
                continue
            if change.object_type == "firewall.address":
                result = self.client.create_address_object(
                    name=str(change.payload["name"]),
                    subnet=str(change.payload["subnet"]),
                    comment=str(change.payload["comment"]),
                )
            elif change.object_type == "firewall.policy":
                result = self.client.create_firewall_policy(change.payload)
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
        return applied

    def _build_changes(
        self,
        request: FortiGatePolicyPreflightRequest,
        address_objects: list[dict[str, Any]],
    ) -> list[FortiGatePolicyObjectChange]:
        existing_addresses = {str(item.get("name")) for item in address_objects}
        source_name = normalize_address_name(request.source_ip)
        changes = [self._address_change(source_name, request.source_ip, existing_addresses)]

        destination_name: str | None = None
        if request.destination_ip:
            destination_name = normalize_address_name(request.destination_ip)
            changes.append(
                self._address_change(destination_name, request.destination_ip, existing_addresses)
            )

        changes.append(
            FortiGatePolicyObjectChange(
                operation="create",
                object_type="firewall.policy",
                name=self._policy_name(request),
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
                "comment": "FortiDashboard owned policy object",
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
            "service": [{"name": request.service or "ALL"}],
            "logtraffic": "all",
            "status": "enable",
            "comments": self._comment(request),
        }

    def _policy_name(self, request: FortiGatePolicyPreflightRequest) -> str:
        prefix = (
            FD_LAB_PREFIX
            if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG
            else FD_TMP_BLOCK_PREFIX
        )
        parts = [prefix, _name_part(request.source_ip)]
        if request.destination_ip:
            parts.extend(["TO", _name_part(request.destination_ip)])
        if request.scope == FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE and request.service:
            parts.append(_name_part(request.service))
        return "_".join(parts)

    def _placement(
        self,
        request: FortiGatePolicyPreflightRequest,
        policies: list[dict[str, Any]],
    ) -> str:
        if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG:
            return "append as FortiDashboard-owned allow/log policy"
        if any(str(policy.get("name") or "").startswith(FD_LAB_PREFIX) for policy in policies):
            return "before first FortiDashboard-owned lab allow/log policy"
        return "append as FortiDashboard-owned temporary block policy"

    def _warnings(
        self,
        request: FortiGatePolicyPreflightRequest,
        policies: list[dict[str, Any]],
    ) -> list[str]:
        if request.intent != FortiGatePolicyIntent.TEMPORARY_BLOCK:
            return []
        if not any(str(policy.get("name") or "").startswith(FD_LAB_PREFIX) for policy in policies):
            return [
                "No FortiDashboard-owned lab allow/log policy was found; "
                "temporary block will be appended."
            ]
        return []

    def _comment(self, request: FortiGatePolicyPreflightRequest) -> str:
        if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG:
            return "FortiDashboard owned lab allow/log policy"
        return "FortiDashboard owned temporary block policy"

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


def _name_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return normalized.strip("_").upper()
