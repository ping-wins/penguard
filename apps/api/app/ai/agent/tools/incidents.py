from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "")}


async def _list_incidents(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    client = ctx.siem_client
    if client is None:
        return {"items": []}
    params = _clean(
        {
            "severity": args.get("severity"),
            "ticketStatus": args.get("ticketStatus") or args.get("ticket_status"),
            "triageLevel": args.get("triageLevel") or args.get("triage_level"),
            "limit": args.get("limit"),
            "ownerUserId": ctx.user_id,
        }
    )
    try:
        payload = client.request("GET", "/incidents", params=params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": []}
    items = payload.get("items") if isinstance(payload, dict) else None
    return {"items": items or [], "count": len(items or [])}


async def _get_incident(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(args.get("incidentId") or args.get("incident_id") or "").strip()
    if not incident_id:
        return {"error": "incidentId is required"}
    client = ctx.siem_client
    if client is None:
        return {"error": "siem client not configured"}
    try:
        payload = client.request("GET", f"/incidents/{incident_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "incidentId": incident_id}
    return payload if isinstance(payload, dict) else {"incident": payload}


register_tool(
    AgentTool(
        name="list_incidents",
        description=(
            "List SOC incidents filtered by severity, ticketStatus or "
            "triageLevel. Use this first to discover incidentIds before "
            "calling get_incident."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["informational", "low", "medium", "high", "critical"],
                },
                "ticketStatus": {
                    "type": "string",
                    "enum": ["new", "investigating", "contained", "closed"],
                },
                "triageLevel": {"type": "string", "enum": ["T1", "T2", "T3"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        impl=_list_incidents,
    )
)

register_tool(
    AgentTool(
        name="get_incident",
        description=(
            "Fetch a full incident record (entities, timeline, ticket "
            "metadata) by id."
        ),
        input_schema={
            "type": "object",
            "required": ["incidentId"],
            "properties": {"incidentId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_get_incident,
    )
)
