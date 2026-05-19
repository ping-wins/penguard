from __future__ import annotations

from typing import Any

import httpx


class EndpointActionClient:
    def __init__(self, *, api_url: str, enrollment_token: str, timeout: float = 5.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.enrollment_token = enrollment_token
        self.timeout = timeout

    def claim_next(self, endpoint_id: str) -> dict[str, Any] | None:
        response = httpx.post(
            f"{self.api_url}/api/weapons/endpoints/{endpoint_id}/actions/claim",
            headers=self._headers(),
            json={},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        action = payload.get("action") if isinstance(payload, dict) else None
        return action if isinstance(action, dict) else None

    def report_result(
        self,
        endpoint_id: str,
        action_id: str,
        *,
        status: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.api_url}/api/weapons/endpoints/{endpoint_id}/actions/{action_id}/result",
            headers=self._headers(),
            json={"status": status, "result": result},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.enrollment_token}"}
