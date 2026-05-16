from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _list_playbook_runs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    client = ctx.soar_client
    if client is None:
        return {"items": []}
    params: dict[str, Any] = {"ownerUserId": ctx.user_id}
    if args.get("status"):
        params["status"] = args["status"]
    if args.get("limit"):
        params["limit"] = int(args["limit"])
    try:
        payload = client.request("GET", "/playbook-runs", params=params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": []}
    items = payload.get("items") if isinstance(payload, dict) else None
    runs = items or []
    return {"items": runs, "count": len(runs)}


register_tool(
    AgentTool(
        name="list_playbook_runs",
        description=(
            "List recent SOAR playbook runs and their status. Useful to "
            "check whether a containment action is already in flight before "
            "proposing a new one."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "running",
                        "completed",
                        "failed",
                        "waiting_approval",
                        "pending_approval",
                    ],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        impl=_list_playbook_runs,
    )
)
