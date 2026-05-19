from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.policies.models import (
    PolicyListResponse,
    PolicyOwnership,
    PolicyProviderSummary,
    PolicyReviewApplyRequest,
    PolicyReviewCreateRequest,
    PolicyReviewResponse,
    PolicyRow,
)

_REVIEWS: dict[str, dict[str, Any]] = {}


class FortiGatePolicyAdapter:
    provider_type = "fortigate"

    def __init__(self, fortigate_service) -> None:
        self.fortigate_service = fortigate_service

    def provider_summary(self, *, owner_user_id: str) -> list[PolicyProviderSummary]:
        items = self.fortigate_service.list(owner_user_id=owner_user_id).get("items", [])
        return [
            PolicyProviderSummary(
                providerType="fortigate",
                integrationId=item["id"],
                name=item.get("name") or item.get("host") or item["id"],
                capabilities=["list", "create", "edit", "enable", "disable", "delete"],
                policyKinds=["firewall_policy", "lab_allow_log", "temporary_block"],
            )
            for item in items
            if item.get("type") in (None, "fortigate")
        ]

    def list_policies(self, *, owner_user_id: str, filters: dict) -> PolicyListResponse:
        integration_id = filters.get("integrationId")
        rows: list[PolicyRow] = []
        integrations = self.fortigate_service.list(owner_user_id=owner_user_id).get("items", [])
        for integration in integrations:
            if integration.get("type") not in (None, "fortigate"):
                continue
            if integration_id and integration["id"] != integration_id:
                continue
            client = self._client(integration["id"], owner_user_id=owner_user_id)
            for policy in client.get_policies():
                rows.append(_row(integration["id"], policy))
        return PolicyListResponse(items=rows, nextCursor=None)

    def create_review(
        self,
        *,
        owner_user_id: str,
        payload: PolicyReviewCreateRequest,
    ) -> PolicyReviewResponse:
        _ = owner_user_id
        review_id = f"fortigate:{_digest(payload.model_dump(mode='json'))[:12]}"
        before = {"summary": "current FortiGate policy state"}
        after = {"summary": f"{payload.action} requested"}
        review_hash = _digest({"id": review_id, "payload": payload.model_dump(mode="json")})
        review = PolicyReviewResponse(
            id=review_id,
            providerType="fortigate",
            integrationId=payload.integration_id,
            policyId=payload.policy_id,
            action=payload.action,
            status="pending_review",
            title=f"{payload.action} FortiGate policy",
            before=before,
            after=after,
            diff=[
                {
                    "field": "status",
                    "before": before["summary"],
                    "after": after["summary"],
                    "risk": "Policy behavior changes",
                }
            ],
            warnings=[
                {
                    "severity": "high",
                    "message": "This may modify an external/customer-owned policy.",
                }
            ],
            rollback=["Run a new review restoring the previous FortiGate policy fields."],
            reviewHash=review_hash,
        )
        _REVIEWS[review_id] = {"review": review, "payload": payload}
        return review

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        stored = _REVIEWS.get(review_id)
        if stored is None:
            raise KeyError("Policy review not found")
        review: PolicyReviewResponse = stored["review"]
        if review.review_hash != payload.review_hash:
            raise ValueError("Stale policy review")
        if not payload.confirmed:
            raise PermissionError("Explicit confirmation is required")

        request_payload: PolicyReviewCreateRequest = stored["payload"]
        client = self._client(review.integration_id, owner_user_id=owner_user_id)
        if request_payload.action == "create":
            result = client.create_firewall_policy(request_payload.payload)
        elif request_payload.action == "disable":
            native_id = _native_policy_id(request_payload.policy_id)
            result = client.update_firewall_policy(native_id, {"status": "disable"})
        elif request_payload.action == "enable":
            native_id = _native_policy_id(request_payload.policy_id)
            result = client.update_firewall_policy(native_id, {"status": "enable"})
        elif request_payload.action == "delete":
            native_id = _native_policy_id(request_payload.policy_id)
            result = client.delete_firewall_policy(native_id)
        elif request_payload.action == "edit":
            native_id = _native_policy_id(request_payload.policy_id)
            result = client.update_firewall_policy(native_id, request_payload.payload)
        else:
            raise ValueError(f"Unsupported FortiGate policy action: {request_payload.action}")
        return {
            "id": review_id,
            "status": "applied",
            "providerType": "fortigate",
            "integrationId": review.integration_id,
            "appliedResult": result,
        }

    def _client(self, integration_id: str, *, owner_user_id: str):
        if hasattr(self.fortigate_service, "get_policy_client"):
            return self.fortigate_service.get_policy_client(
                integration_id=integration_id,
                owner_user_id=owner_user_id,
            )
        return self.fortigate_service.client_for_integration(
            integration_id,
            owner_user_id=owner_user_id,
        )


def _row(integration_id: str, policy: dict[str, Any]) -> PolicyRow:
    native_id = str(policy.get("policyid") or policy.get("id") or policy.get("name"))
    name = str(policy.get("name") or f"Policy {native_id}")
    owned = name.startswith("PG_") or "penguard" in str(
        policy.get("comments") or ""
    ).lower()
    status = "enabled" if policy.get("status") in ("enable", "enabled") else "disabled"
    return PolicyRow(
        id=f"fortigate:{integration_id}:policy:{native_id}",
        providerType="fortigate",
        integrationId=integration_id,
        nativeId=native_id,
        name=name,
        kind="firewall_policy",
        status=status,
        action=str(policy.get("action") or ""),
        direction={
            "source": _names(policy.get("srcintf")),
            "destination": _names(policy.get("dstintf")),
        },
        scope={
            "source": _names(policy.get("srcaddr")),
            "destination": _names(policy.get("dstaddr")),
            "service": _names(policy.get("service")),
        },
        ownership=PolicyOwnership.PENGUARD if owned else PolicyOwnership.EXTERNAL,
        managedByPenguard=owned,
        isMutable=True,
        supports=["edit", "disable" if status == "enabled" else "enable", "delete"],
        risk={"level": "medium", "reasons": ["Firewall policy controls traffic flow"]},
        summary=f"{policy.get('action', 'policy')} {name}",
        lastObservedAt=datetime.now(UTC).isoformat(timespec="milliseconds").replace(
            "+00:00",
            "Z",
        ),
    )


def _names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _native_policy_id(policy_id: str | None) -> str:
    if not policy_id:
        raise ValueError("policyId is required")
    return policy_id.rsplit(":", 1)[-1]


def _digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
