from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _list_integrations(ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    service = ctx.fortigate_integration_service
    if service is None:
        return {"items": []}
    result = service.list(owner_user_id=ctx.user_id)
    items = result.get("items", []) if isinstance(result, dict) else result or []
    normalized: list[dict[str, Any]] = []
    for entry in items:
        if hasattr(entry, "model_dump"):
            normalized.append(entry.model_dump(by_alias=True))
        elif isinstance(entry, dict):
            normalized.append(entry)
        else:
            normalized.append({"value": str(entry)})
    return {"items": normalized}


register_tool(
    AgentTool(
        name="list_integrations",
        description=(
            "Return integrations connected by the current user (FortiGate, "
            "SIEM, XDR, SOAR, FortiWeb). Use it to discover which "
            "integrationId values to pass to other tools."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        impl=_list_integrations,
    )
)
