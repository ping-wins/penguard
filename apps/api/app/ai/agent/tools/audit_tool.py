from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _search_audit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    store = ctx.audit_store
    if store is None:
        return {"items": []}
    limit = int(args.get("limit") or 50)
    limit = max(1, min(limit, 200))
    payload = store.list_events(
        limit=limit,
        actor_user_id=ctx.user_id,
        action=args.get("action") or None,
        outcome=args.get("outcome") or None,
    )
    return payload if isinstance(payload, dict) else {"items": []}


register_tool(
    AgentTool(
        name="search_audit",
        description=(
            "Search the audit log for actions performed by the current "
            "user. Filter by action (e.g. soc.ticket.contained, "
            "integration.fortigate.policy_applied) or outcome "
            "(success|failure)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "outcome": {"type": "string", "enum": ["success", "failure"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        impl=_search_audit,
        required_permissions=frozenset({"audit.read"}),
    )
)
