from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FortiGatePolicyIntent(StrEnum):
    LAB_ALLOW_LOG = "lab_allow_log"
    TEMPORARY_BLOCK = "temporary_block"


class FortiGatePolicyScope(StrEnum):
    SOURCE_ONLY = "source_only"
    SOURCE_DESTINATION = "source_destination"
    SOURCE_DESTINATION_SERVICE = "source_destination_service"


class FortiGatePolicyAction(StrEnum):
    ACCEPT = "accept"
    DENY = "deny"


class FortiGatePolicyPreflightRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    intent: FortiGatePolicyIntent
    scope: FortiGatePolicyScope
    source_interface: str = Field(min_length=1, max_length=64)
    destination_interface: str = Field(min_length=1, max_length=64)
    source_ip: str = Field(min_length=3, max_length=128)
    destination_ip: str | None = Field(default=None, min_length=3, max_length=128)
    service: str | None = Field(default=None, min_length=1, max_length=128)
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    incident_id: str | None = None
    playbook_run_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> FortiGatePolicyPreflightRequest:
        if self.scope in {
            FortiGatePolicyScope.SOURCE_DESTINATION,
            FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
        } and not self.destination_ip:
            raise ValueError("destination_ip is required for this scope")
        if self.scope == FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE and not self.service:
            raise ValueError("service is required for source_destination_service scope")
        return self


class FortiGatePolicyObjectChange(BaseModel):
    operation: Literal["create", "reuse", "update"]
    object_type: Literal["firewall.address", "firewall.policy"]
    name: str
    payload: dict[str, Any]


class FortiGatePolicyPreflightResponse(BaseModel):
    intent: FortiGatePolicyIntent
    scope: FortiGatePolicyScope
    integration_id: str
    existing_policy_count: int
    owned_policy_count: int
    proposed_policy_name: str
    placement: str
    warnings: list[str] = Field(default_factory=list)
    changes: list[FortiGatePolicyObjectChange]
    review_hash: str


class FortiGatePolicyReviewRequest(FortiGatePolicyPreflightRequest):
    pass


class FortiGatePolicyReviewResponse(FortiGatePolicyPreflightResponse):
    request_id: str
    status: Literal["pending_review"]
    expires_at: datetime | None = None


class FortiGatePolicyApplyRequest(BaseModel):
    request_id: str
    review_hash: str


class FortiGatePolicyApplyResponse(BaseModel):
    request_id: str
    status: Literal["applied"]
    applied_changes: list[dict[str, Any]]
