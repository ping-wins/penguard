from __future__ import annotations

from fastapi import HTTPException, status

from app.policies.adapters import PolicyProviderAdapter
from app.policies.models import (
    PolicyListResponse,
    PolicyReviewApplyRequest,
    PolicyReviewCreateRequest,
)


class PolicyService:
    def __init__(self, adapters: list[PolicyProviderAdapter]) -> None:
        self.adapters = {adapter.provider_type: adapter for adapter in adapters}

    def list_providers(self, *, owner_user_id: str) -> dict:
        items = []
        for adapter in self.adapters.values():
            items.extend(
                item.model_dump(mode="json", by_alias=True)
                for item in adapter.provider_summary(owner_user_id=owner_user_id)
            )
        return {"items": items}

    def list_policies(self, *, owner_user_id: str, filters: dict) -> dict:
        provider_type = filters.get("providerType")
        adapters = [self._adapter(provider_type)] if provider_type else list(self.adapters.values())
        rows = []
        for adapter in adapters:
            result: PolicyListResponse = adapter.list_policies(
                owner_user_id=owner_user_id,
                filters=filters,
            )
            rows.extend(row.model_dump(mode="json", by_alias=True) for row in result.items)
        return {"items": rows, "nextCursor": None}

    def create_review(self, *, owner_user_id: str, payload: PolicyReviewCreateRequest) -> dict:
        review = self._adapter(payload.provider_type).create_review(
            owner_user_id=owner_user_id,
            payload=payload,
        )
        return review.model_dump(mode="json", by_alias=True)

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        provider_type = review_id.split(":", 1)[0] if ":" in review_id else "fortigate"
        return self._adapter(provider_type).apply_review(
            owner_user_id=owner_user_id,
            review_id=review_id,
            payload=payload,
        )

    def _adapter(self, provider_type: str | None) -> PolicyProviderAdapter:
        if not provider_type or provider_type not in self.adapters:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy provider not available",
            )
        return self.adapters[provider_type]
