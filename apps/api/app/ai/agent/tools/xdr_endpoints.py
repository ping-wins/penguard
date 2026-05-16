from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _get_endpoint(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    endpoint_id = str(args.get("endpointId") or args.get("endpoint_id") or "").strip()
    if not endpoint_id:
        return {"error": "endpointId is required"}
    client = ctx.xdr_client
    if client is None:
        return {"error": "xdr client not configured"}
    try:
        payload = client.request(
            "GET",
            f"/endpoints/{endpoint_id}",
            params={"ownerUserId": ctx.user_id},
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "endpointId": endpoint_id}
    return payload if isinstance(payload, dict) else {"endpoint": payload}


register_tool(
    AgentTool(
        name="get_endpoint",
        description=(
            "Fetch full XDR endpoint detail (health, latest heartbeat, "
            "recent processes / connections) by endpointId."
        ),
        input_schema={
            "type": "object",
            "required": ["endpointId"],
            "properties": {"endpointId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_get_endpoint,
    )
)
