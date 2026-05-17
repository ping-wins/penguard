from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PolicyProviderType(StrEnum):
    FORTIGATE = "fortigate"
    FORTIWEB = "fortiweb"


class PolicyAction(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"


class PolicyOwnership(StrEnum):
    FORTIDASHBOARD = "fortidashboard"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class PolicyProviderSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    name: str
    capabilities: list[str]
    policy_kinds: list[str] = Field(alias="policyKinds")


class PolicyRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    native_id: str = Field(alias="nativeId")
    name: str
    kind: str
    status: str
    action: str | None = None
    direction: dict[str, Any] = Field(default_factory=dict)
    scope: dict[str, Any] = Field(default_factory=dict)
    ownership: PolicyOwnership = PolicyOwnership.UNKNOWN
    managed_by_fortidashboard: bool = Field(default=False, alias="managedByFortiDashboard")
    is_mutable: bool = Field(default=False, alias="isMutable")
    supports: list[str] = Field(default_factory=list)
    risk: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    last_observed_at: str | None = Field(default=None, alias="lastObservedAt")
    raw: dict[str, Any] | None = None


class PolicyListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[PolicyRow]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class PolicyReviewCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    action: PolicyAction
    policy_id: str | None = Field(default=None, alias="policyId")
    payload: dict[str, Any] = Field(default_factory=dict)


class PolicyReviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    policy_id: str | None = Field(default=None, alias="policyId")
    action: PolicyAction
    status: Literal["pending_review", "applied", "failed"]
    title: str
    before: dict[str, Any]
    after: dict[str, Any]
    diff: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    rollback: list[str]
    review_hash: str = Field(alias="reviewHash")


class PolicyReviewApplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    review_hash: str = Field(alias="reviewHash")
    confirmed: bool
