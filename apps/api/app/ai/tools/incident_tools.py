"""Synchronous incident management tools for the cockpit chat agent.

These mirror the agent runtime tools under `app.ai.agent.tools.incidents`
but stay synchronous so they can be invoked from the single-turn cockpit
chat without an async runtime. They are the safe read/draft surface the
chat exposes to the LLM-routed user requests.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.soc.client import SocServiceClient


def _siem_client() -> SocServiceClient:
    settings = get_settings()
    return SocServiceClient(
        base_url=settings.siem_kowalski_url,
        service_name="siem_kowalski",
        timeout_seconds=5.0,
    )


def _soar_client() -> SocServiceClient:
    settings = get_settings()
    return SocServiceClient(
        base_url=settings.soar_skipper_url,
        service_name="soar_skipper",
        timeout_seconds=5.0,
    )


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "")}


def list_incidents(
    *,
    user_id: str | None = None,
    limit: int = 10,
    severity: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List recent SIEM incidents scoped to the caller."""
    params = _clean(
        {
            "limit": limit,
            "severity": severity,
            "status": status,
            "ownerUserId": user_id,
        }
    )
    try:
        payload = _siem_client().request("GET", "/incidents", params=params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": [], "count": 0}
    items = payload.get("items") if isinstance(payload, dict) else None
    items = items or []
    return {"items": items, "count": len(items)}


def get_incident(incident_id: str, *, user_id: str | None = None) -> dict[str, Any]:
    """Fetch a single incident by id with full payload."""
    if not incident_id.strip():
        return {"error": "incidentId is required"}
    params = _clean({"ownerUserId": user_id})
    try:
        payload = _siem_client().request(
            "GET", f"/incidents/{incident_id}", params=params
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return payload if isinstance(payload, dict) else {"error": "Unexpected payload"}


def update_incident_status(
    incident_id: str,
    *,
    user_id: str | None = None,
    status: str,
    triage_level: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark an incident as `open`, `acknowledged`, `resolved` or `closed`.
    Returns a draft preview when called without the explicit `confirm`
    flag — the caller (chat UI) is expected to surface the diff and ask
    the user to confirm before persisting."""
    if not incident_id.strip():
        return {"error": "incidentId is required"}
    if status not in {"open", "acknowledged", "in_progress", "resolved", "closed"}:
        return {"error": f"unsupported status: {status}"}
    body = _clean(
        {
            "status": status,
            "triageLevel": triage_level,
            "note": note,
            "ownerUserId": user_id,
        }
    )
    try:
        payload = _siem_client().request(
            "PATCH", f"/incidents/{incident_id}", json=body
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return payload if isinstance(payload, dict) else {"error": "Unexpected payload"}


def draft_containment_playbook(
    *,
    user_id: str | None = None,
    ticket_id: str,
) -> dict[str, Any]:
    """Build a SOAR containment playbook draft for the given ticket. The
    draft is not executed — the chat surfaces it for review."""
    if not ticket_id.strip():
        return {"error": "ticketId is required"}
    body = _clean({"ownerUserId": user_id})
    try:
        payload = _soar_client().request(
            "POST", f"/tickets/{ticket_id}/draft-playbook", json=body
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return payload if isinstance(payload, dict) else {"error": "Unexpected payload"}


__all__ = [
    "list_incidents",
    "get_incident",
    "update_incident_status",
    "draft_containment_playbook",
]
