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
DEFAULT_WAF_DOS_INLINE_PROFILE = "Penguard Inline DoS Protection"


class FortiWebPolicyAdapter:
    provider_type = "fortiweb"

    def __init__(self, fortiweb_service) -> None:
        self.fortiweb_service = fortiweb_service

    def provider_summary(self, *, owner_user_id: str) -> list[PolicyProviderSummary]:
        return [
            PolicyProviderSummary(
                providerType="fortiweb",
                integrationId=item["id"],
                name=item.get("name") or item.get("host") or item["id"],
                capabilities=["list", "create", "edit", "delete"],
                policyKinds=["server_policy", "ip_blocklist", "source_block"],
            )
            for item in self._integrations(owner_user_id=owner_user_id)
        ]

    def list_policies(self, *, owner_user_id: str, filters: dict) -> PolicyListResponse:
        integration_filter = filters.get("integrationId")
        rows: list[PolicyRow] = []
        for integration in self._integrations(owner_user_id=owner_user_id):
            integration_id = integration["id"]
            if integration_filter and integration_id != integration_filter:
                continue
            rows.extend(_configured_policy_rows(integration))
            rows.extend(
                _block_row(integration_id=integration_id, block=block)
                for block in self.fortiweb_service.list_blocks(
                    owner_user_id=owner_user_id,
                    integration_id=integration_id,
                ).get("items", [])
            )
        return PolicyListResponse(items=rows, nextCursor=None)

    def create_review(
        self,
        *,
        owner_user_id: str,
        payload: PolicyReviewCreateRequest,
    ) -> PolicyReviewResponse:
        if payload.action == "create":
            review = self.fortiweb_service.review_source_block(
                owner_user_id=owner_user_id,
                integration_id=payload.integration_id,
                source_ip=_source_ip(payload.payload),
                incident_id=_nullable_string(payload.payload.get("incidentId")),
                reason=_nullable_string(payload.payload.get("reason")),
            )
            response = _create_block_review_response(review)
            _REVIEWS[response.id] = {
                "action": "create",
                "blockId": review["id"],
                "review": response,
            }
            return response
        if (
            payload.action == "edit"
            and payload.payload.get("operation") == "prepare_waf_dos_policy"
        ):
            review = self.fortiweb_service.review_waf_dos_policy(
                owner_user_id=owner_user_id,
                integration_id=payload.integration_id,
                target_server_policy=_target_server_policy(payload),
                inline_protection_profile=str(
                    payload.payload.get("inlineProtectionProfile")
                    or DEFAULT_WAF_DOS_INLINE_PROFILE
                ),
                dos_prevention_policy=str(
                    payload.payload.get("dosPreventionPolicy") or "Predefined"
                ),
                reason=_nullable_string(payload.payload.get("reason")),
            )
            response = _create_waf_dos_review_response(review, policy_id=payload.policy_id)
            _REVIEWS[response.id] = {
                "action": "prepare_waf_dos_policy",
                "reviewPayload": review,
                "review": response,
            }
            return response
        if payload.action == "delete":
            block_id = _native_block_id(payload.policy_id)
            review_hash = _digest(
                {
                    "action": "delete",
                    "providerType": "fortiweb",
                    "integrationId": payload.integration_id,
                    "blockId": block_id,
                    "payload": payload.payload,
                }
            )
            response = PolicyReviewResponse(
                id=f"fortiweb:delete:{block_id}:{review_hash[:12]}",
                providerType="fortiweb",
                integrationId=payload.integration_id,
                policyId=payload.policy_id,
                action=payload.action,
                status="pending_review",
                title="Remove FortiWeb source block",
                before={"summary": f"FortiWeb source block {block_id} is active"},
                after={"summary": "FortiWeb source block will be removed"},
                diff=[
                    {
                        "field": "status",
                        "before": "active",
                        "after": "removed",
                        "risk": "Previously blocked source may reach the WAF policy again",
                    }
                ],
                warnings=[],
                rollback=["Create a new FortiWeb source-block review for the same IP if needed."],
                reviewHash=review_hash,
            )
            _REVIEWS[response.id] = {
                "action": "delete",
                "blockId": block_id,
                "review": response,
            }
            return response
        raise ValueError(f"Unsupported FortiWeb policy action: {payload.action}")

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

        if stored["action"] == "create":
            block_id = str(stored["blockId"])
            result = self.fortiweb_service.apply_source_block(
                owner_user_id=owner_user_id,
                block_id=block_id,
                review_hash=payload.review_hash,
                confirmed=True,
            )
        elif stored["action"] == "prepare_waf_dos_policy":
            result = self.fortiweb_service.apply_waf_dos_policy(
                owner_user_id=owner_user_id,
                review=stored["reviewPayload"],
                review_hash=payload.review_hash,
                confirmed=True,
            )
        elif stored["action"] == "delete":
            block_id = str(stored["blockId"])
            result = self.fortiweb_service.remove_source_block(
                owner_user_id=owner_user_id,
                block_id=block_id,
            )
        else:
            raise ValueError(f"Unsupported FortiWeb review action: {stored['action']}")
        return {
            "id": review_id,
            "status": "applied",
            "providerType": "fortiweb",
            "integrationId": review.integration_id,
            "appliedResult": result,
        }

    def _integrations(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.fortiweb_service.list(owner_user_id=owner_user_id).get("items", [])
            if item.get("type") == "fortiweb"
        ]


def _configured_policy_rows(integration: dict[str, Any]) -> list[PolicyRow]:
    integration_id = str(integration["id"])
    observed_at = _observed_at()
    rows: list[PolicyRow] = []
    target_policy = _nullable_string(integration.get("targetServerPolicy"))
    if target_policy:
        rows.append(
            PolicyRow(
                id=f"fortiweb:{integration_id}:server-policy:{target_policy}",
                providerType="fortiweb",
                integrationId=integration_id,
                nativeId=target_policy,
                name=target_policy,
                kind="server_policy",
                status="enabled",
                action="waf",
                direction={},
                scope={"serverPolicy": target_policy},
                ownership=PolicyOwnership.EXTERNAL,
                managedByPenguard=False,
                isMutable=True,
                supports=["edit"],
                risk={"level": "medium", "reasons": ["WAF policy controls protected traffic"]},
                summary=f"FortiWeb server policy {target_policy}",
                lastObservedAt=observed_at,
                raw={
                    "targetServerPolicy": target_policy,
                    "managedIpListPolicy": integration.get("managedIpListPolicy"),
                },
            )
        )
    ip_list_policy = _nullable_string(integration.get("managedIpListPolicy"))
    if ip_list_policy:
        owned = ip_list_policy.startswith("PG_")
        rows.append(
            PolicyRow(
                id=f"fortiweb:{integration_id}:ip-list:{ip_list_policy}",
                providerType="fortiweb",
                integrationId=integration_id,
                nativeId=ip_list_policy,
                name=ip_list_policy,
                kind="ip_blocklist",
                status="enabled",
                action="block",
                direction={},
                scope={"serverPolicy": target_policy, "ipListPolicy": ip_list_policy},
                ownership=PolicyOwnership.PENGUARD
                if owned
                else PolicyOwnership.EXTERNAL,
                managedByPenguard=owned,
                isMutable=owned,
                supports=[],
                risk={"level": "high", "reasons": ["IP list can deny traffic to protected apps"]},
                summary=f"FortiWeb managed IP list {ip_list_policy}",
                lastObservedAt=observed_at,
                raw={
                    "targetServerPolicy": target_policy,
                    "managedIpListPolicy": ip_list_policy,
                },
            )
        )
    return rows


def _block_row(*, integration_id: str, block: dict[str, Any]) -> PolicyRow:
    block_id = str(block.get("id") or block.get("sourceIp") or "unknown")
    source_ip = str(block.get("sourceIp") or block_id)
    intent = block.get("intent") if isinstance(block.get("intent"), dict) else {}
    status = "enabled" if block.get("status") == "active" else str(block.get("status") or "unknown")
    return PolicyRow(
        id=f"fortiweb:{integration_id}:block:{block_id}",
        providerType="fortiweb",
        integrationId=integration_id,
        nativeId=block_id,
        name=f"Block {source_ip}",
        kind="source_block",
        status=status,
        action="block",
        direction={},
        scope={
            "source": [source_ip],
            "serverPolicy": intent.get("targetServerPolicy"),
            "ipListPolicy": intent.get("managedIpListPolicy"),
            "incidentId": block.get("incidentId"),
        },
        ownership=PolicyOwnership.PENGUARD,
        managedByPenguard=True,
        isMutable=block.get("status") == "active",
        supports=["delete"] if block.get("status") == "active" else [],
        risk={"level": "high", "reasons": ["Source IP is denied by FortiWeb"]},
        summary=f"FortiWeb source block {source_ip}",
        lastObservedAt=_nullable_string(block.get("updatedAt") or block.get("createdAt")),
        raw=block,
    )


def _create_block_review_response(review: dict[str, Any]) -> PolicyReviewResponse:
    source_ip = str(review.get("sourceIp") or "")
    proposed_changes = review.get("proposedChanges")
    if not isinstance(proposed_changes, list):
        proposed_changes = []
    raw_preflight = review.get("preflightSummary")
    preflight = raw_preflight if isinstance(raw_preflight, dict) else {}
    warnings = []
    if preflight.get("alreadyBlocked"):
        warnings.append({"severity": "info", "message": "Source IP is already blocked"})
    return PolicyReviewResponse(
        id=f"fortiweb:{review['id']}",
        providerType="fortiweb",
        integrationId=review["integrationId"],
        policyId=f"fortiweb:{review['integrationId']}:block:{review['id']}",
        action="create",
        status="pending_review",
        title="Create FortiWeb source block",
        before={"summary": "current FortiWeb IP-list policy state", **preflight},
        after={"summary": f"{source_ip} will be blocked by FortiWeb", "sourceIp": source_ip},
        diff=[
            {
                "field": str(change.get("operation") or "policy"),
                "before": "current",
                "after": change.get("summary") or change,
                "risk": "FortiWeb policy behavior changes",
            }
            for change in proposed_changes
            if isinstance(change, dict)
        ],
        warnings=warnings,
        rollback=["Remove the source block from the FortiWeb policy manager."],
        reviewHash=review["reviewHash"],
    )


def _create_waf_dos_review_response(
    review: dict[str, Any],
    *,
    policy_id: str | None,
) -> PolicyReviewResponse:
    proposed_changes = review.get("proposedChanges")
    if not isinstance(proposed_changes, list):
        proposed_changes = []
    preflight = review.get("preflightSummary")
    if not isinstance(preflight, dict):
        preflight = {}
    no_changes = not proposed_changes
    warnings = []
    if no_changes:
        warnings.append(
            {
                "severity": "info",
                "message": "FortiWeb WAF/DoS policy is already prepared",
            }
        )
    return PolicyReviewResponse(
        id=f"fortiweb:waf-dos:{review['id']}",
        providerType="fortiweb",
        integrationId=review["integrationId"],
        policyId=policy_id,
        action="edit",
        status="pending_review",
        title="Prepare FortiWeb WAF/DoS policy",
        before={"summary": "current FortiWeb WAF/DoS policy state", **preflight},
        after={
            "summary": "FortiWeb server policy will use inline WAF protection and DoS prevention",
            "targetServerPolicy": preflight.get("serverPolicy"),
            "inlineProtectionProfile": preflight.get("desiredInlineProtectionProfile"),
            "dosPreventionPolicy": preflight.get("desiredDosPreventionPolicy"),
        },
        diff=[
            {
                "field": str(change.get("operation") or change.get("field") or "policy"),
                "before": change.get("before"),
                "after": change.get("after") or change.get("summary") or change,
                "risk": "FortiWeb WAF/DoS policy behavior changes",
            }
            for change in proposed_changes
            if isinstance(change, dict)
        ],
        warnings=warnings,
        rollback=[
            "Run a new Penguard policy review restoring the previous FortiWeb profile fields."
        ],
        reviewHash=review["reviewHash"],
    )


def _source_ip(payload: dict[str, Any]) -> str:
    value = payload.get("sourceIp") or payload.get("source_ip")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("sourceIp is required for FortiWeb source-block reviews")
    return value.strip()


def _target_server_policy(payload: PolicyReviewCreateRequest) -> str | None:
    value = payload.payload.get("targetServerPolicy")
    if isinstance(value, str) and value.strip():
        return value.strip()
    policy_id = payload.policy_id
    if policy_id and ":server-policy:" in policy_id:
        return policy_id.rsplit(":server-policy:", 1)[-1]
    return None


def _nullable_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _native_block_id(policy_id: str | None) -> str:
    if not policy_id:
        raise ValueError("policyId is required")
    return policy_id.rsplit(":", 1)[-1]


def _observed_at() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
