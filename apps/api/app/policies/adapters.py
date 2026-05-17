from __future__ import annotations

from typing import Protocol

from app.policies.models import (
    PolicyListResponse,
    PolicyProviderSummary,
    PolicyReviewApplyRequest,
    PolicyReviewCreateRequest,
    PolicyReviewResponse,
)


class PolicyProviderAdapter(Protocol):
    provider_type: str

    def provider_summary(self, *, owner_user_id: str) -> list[PolicyProviderSummary]:
        pass

    def list_policies(self, *, owner_user_id: str, filters: dict) -> PolicyListResponse:
        pass

    def create_review(
        self,
        *,
        owner_user_id: str,
        payload: PolicyReviewCreateRequest,
    ) -> PolicyReviewResponse:
        pass

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        pass
