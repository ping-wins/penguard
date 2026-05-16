from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


async def _get_widget_data(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    widget_id = str(args.get("widgetId") or args.get("widget_id") or "").strip()
    integration_id = str(args.get("integrationId") or args.get("integration_id") or "").strip()
    if not widget_id:
        return {"error": "widgetId is required"}
    service = ctx.fortigate_widget_service
    if service is None:
        return {"error": "fortigate widget service not configured"}
    try:
        payload = service.get_widget_data(
            widget_id,
            integration_id or None,
            owner_user_id=ctx.user_id,
        )
    except KeyError:
        return {"error": "widget data not found", "widgetId": widget_id}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "widgetId": widget_id}
    return {"widgetId": widget_id, "data": payload}


register_tool(
    AgentTool(
        name="get_widget_data",
        description=(
            "Fetch the current payload for a dashboard widget. Pass widgetId "
            "(e.g. fortigate-system-status, soc-incidents-by-severity) and "
            "integrationId when the widget binds to a specific integration."
        ),
        input_schema={
            "type": "object",
            "required": ["widgetId"],
            "properties": {
                "widgetId": {"type": "string"},
                "integrationId": {"type": "string"},
            },
            "additionalProperties": False,
        },
        impl=_get_widget_data,
    )
)
