from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _get_workspace(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    store = ctx.workspace_store
    if store is None:
        return {"error": "workspace store not configured"}
    workspace_id = str(args.get("workspaceId") or args.get("workspace_id") or "").strip()
    try:
        if workspace_id:
            payload = store.get_workspace(
                workspace_id=workspace_id, owner_user_id=ctx.user_id
            )
        else:
            workspaces = store.list_workspaces(owner_user_id=ctx.user_id) or []
            payload = workspaces[0] if workspaces else None
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    if payload is None:
        return {"error": "workspace not found"}
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(by_alias=True)
    return payload if isinstance(payload, dict) else {"workspace": payload}


async def _search_events(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    client = ctx.siem_client
    if client is None:
        return {"items": []}
    params: dict[str, Any] = {"ownerUserId": ctx.user_id}
    for key in ("source", "eventType", "severity", "since", "until"):
        if args.get(key):
            params[key] = args[key]
    if args.get("limit"):
        params["limit"] = int(args["limit"])
    try:
        payload = client.request("GET", "/events", params=params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": []}
    items = payload.get("items") if isinstance(payload, dict) else None
    return {"items": items or [], "count": len(items or [])}


register_tool(
    AgentTool(
        name="get_workspace",
        description=(
            "Return the cockpit workspace layout (widgets + bindings) for "
            "the current user. Pass workspaceId to target a specific "
            "workspace, otherwise the first one is returned."
        ),
        input_schema={
            "type": "object",
            "properties": {"workspaceId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_get_workspace,
    )
)

register_tool(
    AgentTool(
        name="search_events",
        description=(
            "Search SIEM events filtered by source (fortigate, fortiweb, "
            "xdr_rico), eventType, severity, or a time window."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "eventType": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["informational", "low", "medium", "high", "critical"],
                },
                "since": {"type": "string", "description": "ISO8601 lower bound"},
                "until": {"type": "string", "description": "ISO8601 upper bound"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        impl=_search_events,
    )
)
