from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "")}


def _siem_client(ctx: ToolContext):
    if ctx.siem_client is None:
        raise RuntimeError("siem client not configured")
    return ctx.siem_client


async def _list_tickets(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = _clean(
        {
            "ticketStatus": args.get("status")
            or args.get("ticketStatus")
            or args.get("ticket_status"),
            "triageLevel": args.get("triage") or args.get("triageLevel"),
            "severity": args.get("severity"),
        }
    )
    if args.get("limit"):
        params["limit"] = int(args["limit"])
    try:
        payload = _siem_client(ctx).request("GET", "/incidents", params=params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": []}
    items = payload.get("items") if isinstance(payload, dict) else payload
    rows = items if isinstance(items, list) else []
    return {"items": rows, "count": len(rows)}


async def _get_ticket(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    ticket_id = str(args.get("ticketId") or args.get("ticket_id") or "").strip()
    if not ticket_id:
        return {"error": "ticketId is required"}
    try:
        payload = _siem_client(ctx).request("GET", f"/incidents/{ticket_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "ticketId": ticket_id}
    return payload if isinstance(payload, dict) else {"ticket": payload}


async def _update_ticket(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    ticket_id = str(args.get("ticketId") or args.get("ticket_id") or "").strip()
    if not ticket_id:
        return {"error": "ticketId is required"}
    allowed_aliases = {
        "triageLevel": ("triageLevel", "triage_level", "triage"),
        "ticketStatus": ("ticketStatus", "ticket_status", "status"),
        "assigneeUserId": ("assigneeUserId", "assignee_user_id"),
        "aiAnalysisId": ("aiAnalysisId", "ai_analysis_id"),
        "note": ("note",),
    }
    body: dict[str, Any] = {}
    for canonical, aliases in allowed_aliases.items():
        for alias in aliases:
            value = args.get(alias)
            if value not in (None, ""):
                body[canonical] = value
                break
    if not body:
        return {
            "error": (
                "one of triageLevel, ticketStatus, assigneeUserId, "
                "aiAnalysisId or note is required"
            ),
            "ticketId": ticket_id,
        }
    try:
        payload = _siem_client(ctx).request(
            "PATCH",
            f"/incidents/{ticket_id}/triage",
            json=body,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "ticketId": ticket_id}
    return payload if isinstance(payload, dict) else {"ticket": payload}


async def _update_incident_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(args.get("incidentId") or args.get("incident_id") or "").strip()
    status = str(args.get("status") or "").strip()
    if not incident_id:
        return {"error": "incidentId is required"}
    if not status:
        return {"error": "status is required", "incidentId": incident_id}
    try:
        payload = _siem_client(ctx).request(
            "PATCH",
            f"/incidents/{incident_id}",
            json={"status": status},
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "incidentId": incident_id}
    return payload if isinstance(payload, dict) else {"incident": payload}


register_tool(
    AgentTool(
        name="list_tickets",
        description="List SOC tickets backed by SIEM incidents and triage metadata.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["new", "investigating", "contained", "closed"],
                },
                "triage": {"type": "string", "enum": ["T1", "T2", "T3"]},
                "severity": {
                    "type": "string",
                    "enum": ["informational", "low", "medium", "high", "critical"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        impl=_list_tickets,
    )
)


register_tool(
    AgentTool(
        name="get_ticket",
        description="Fetch one SOC ticket with incident timeline and triage metadata.",
        input_schema={
            "type": "object",
            "required": ["ticketId"],
            "properties": {"ticketId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_get_ticket,
    )
)


register_tool(
    AgentTool(
        name="update_ticket",
        description=(
            "Update ticket triage metadata, status, assignee, linked AI "
            "analysis or append a note after analyst approval."
        ),
        input_schema={
            "type": "object",
            "required": ["ticketId"],
            "properties": {
                "ticketId": {"type": "string"},
                "triageLevel": {"type": "string", "enum": ["T1", "T2", "T3"]},
                "ticketStatus": {
                    "type": "string",
                    "enum": ["new", "investigating", "contained", "closed"],
                },
                "assigneeUserId": {"type": "string"},
                "aiAnalysisId": {"type": "string"},
                "note": {"type": "string"},
            },
            "additionalProperties": False,
        },
        impl=_update_ticket,
        category="write",
        requires_approval=True,
        required_permissions=frozenset({"tickets.manage"}),
    )
)


register_tool(
    AgentTool(
        name="update_incident_status",
        description=(
            "Update the workflow status of a SOC incident after analyst "
            "approval. Use update_ticket for ticket triage metadata."
        ),
        input_schema={
            "type": "object",
            "required": ["incidentId", "status"],
            "properties": {
                "incidentId": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["open", "triaged", "contained", "resolved", "false_positive"],
                },
            },
            "additionalProperties": False,
        },
        impl=_update_incident_status,
        category="write",
        requires_approval=True,
        required_permissions=frozenset({"tickets.manage"}),
    )
)
