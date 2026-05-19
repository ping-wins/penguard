from __future__ import annotations

from secrets import token_urlsafe
from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool

GRID_COLUMN_PX = 100
GRID_ROW_PX = 90
GRID_PADDING_PX = 20

VISUAL_TEMPLATE_ID_BY_DRAFT_TYPE: dict[str, str] = {
    "card": "visual-template-card",
    "kpi": "visual-template-card",
    "gauge": "visual-template-gauge",
    "bar": "visual-template-bar",
    "chart": "visual-template-bar",
    "line": "visual-template-line",
    "table": "visual-template-table",
    "feed": "visual-template-feed",
    "list": "visual-template-list",
    "status-list": "visual-template-list",
    "risk-summary": "visual-template-list",
}


def _workspace_get(store: Any, workspace_id: str, *, owner_user_id: str) -> dict | None:
    if hasattr(store, "get"):
        return store.get(workspace_id, owner_user_id=owner_user_id)
    return store.get_workspace(workspace_id=workspace_id, owner_user_id=owner_user_id)


def _active_workspace_id(ctx: ToolContext, args: dict[str, Any]) -> str:
    return str(
        args.get("workspaceId")
        or args.get("workspace_id")
        or ctx.extras.get("activeWorkspaceId")
        or ctx.extras.get("active_workspace_id")
        or ""
    ).strip()


def _default_workspace_id(store: Any, *, owner_user_id: str) -> str:
    try:
        workspaces = store.list_workspaces(owner_user_id=owner_user_id) or []
    except Exception:  # noqa: BLE001
        workspaces = []
    first = workspaces[0] if workspaces and isinstance(workspaces[0], dict) else None
    return str(first.get("id") or "ws_default") if first else "ws_default"


def _workspace_for_write(ctx: ToolContext, args: dict[str, Any]) -> tuple[str, dict]:
    store = ctx.workspace_store
    if store is None:
        raise RuntimeError("workspace store not configured")
    workspace_id = _active_workspace_id(ctx, args) or _default_workspace_id(
        store,
        owner_user_id=ctx.user_id,
    )
    workspace = _workspace_get(store, workspace_id, owner_user_id=ctx.user_id)
    if workspace is None:
        workspace = {"id": workspace_id, "name": "SOC Overview", "widgets": []}
    if hasattr(workspace, "model_dump"):
        workspace = workspace.model_dump(by_alias=True)
    if not isinstance(workspace, dict):
        raise RuntimeError("workspace store returned invalid workspace")
    return workspace_id, workspace


def _grid_size_to_pixels(width: int, height: int) -> dict[str, int]:
    return {
        "w": width * GRID_COLUMN_PX + GRID_PADDING_PX,
        "h": height * GRID_ROW_PX + GRID_PADDING_PX,
    }


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _non_negative_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _layout_for_widget(
    *,
    args: dict[str, Any],
    draft: dict[str, Any],
    widgets: list[dict[str, Any]],
) -> dict[str, int]:
    raw_layout = args.get("layout") if isinstance(args.get("layout"), dict) else {}
    draft_layout = draft.get("layout") if isinstance(draft.get("layout"), dict) else {}
    position = args.get("position") if isinstance(args.get("position"), dict) else {}
    max_z = max(
        [100]
        + [
            _positive_int(widget.get("layout", {}).get("z"), 100)
            for widget in widgets
            if isinstance(widget, dict) and isinstance(widget.get("layout"), dict)
        ]
    )
    width = _positive_int(raw_layout.get("w"), _positive_int(draft_layout.get("w"), 3))
    height = _positive_int(raw_layout.get("h"), _positive_int(draft_layout.get("h"), 2))
    size = (
        _grid_size_to_pixels(width, height)
        if width <= 24 and height <= 24
        else {"w": width, "h": height}
    )
    return {
        "x": _non_negative_int(position.get("x", raw_layout.get("x")), 50),
        "y": _non_negative_int(position.get("y", raw_layout.get("y")), 50),
        **size,
        "z": max_z + 1,
    }


def _field_bindings_for_widget(
    *,
    args: dict[str, Any],
    draft: dict[str, Any],
    integration_id: str,
    provider: str,
) -> list[dict[str, Any]]:
    raw_bindings = args.get("fieldBindings") or args.get("field_bindings")
    if not isinstance(raw_bindings, list):
        raw_bindings = draft.get("fieldBindings") or draft.get("field_bindings") or []
    bindings: list[dict[str, Any]] = []
    for raw in raw_bindings:
        if not isinstance(raw, dict):
            continue
        field_id = str(raw.get("fieldId") or raw.get("field_id") or "").strip()
        if not field_id:
            continue
        binding_provider = str(raw.get("provider") or provider or "").strip()
        binding = {
            "fieldId": field_id,
            "label": str(raw.get("label") or field_id),
            "type": str(raw.get("type") or "string"),
            "source": str(raw.get("source") or ""),
            "provider": binding_provider,
            "integrationId": str(raw.get("integrationId") or integration_id or ""),
            "integrationType": str(raw.get("integrationType") or binding_provider),
        }
        for optional in ("unit", "groupId", "groupName"):
            value = raw.get(optional)
            if value not in (None, ""):
                binding[optional] = str(value)
        bindings.append(binding)
    return bindings


def _catalog_id_for_widget(args: dict[str, Any], draft: dict[str, Any]) -> str:
    explicit = str(args.get("catalogId") or args.get("catalog_id") or "").strip()
    if explicit:
        return explicit
    visual_type = str(
        args.get("visualType")
        or args.get("visual_type")
        or draft.get("visualType")
        or draft.get("visual_type")
        or ""
    ).strip()
    catalog_id = VISUAL_TEMPLATE_ID_BY_DRAFT_TYPE.get(visual_type)
    if not catalog_id:
        raise RuntimeError("catalogId or supported visualType is required")
    return catalog_id


def _record_summon_audit(
    ctx: ToolContext,
    *,
    workspace_id: str,
    widget: dict[str, Any],
) -> None:
    if ctx.audit_store is None:
        return
    ctx.audit_store.record(
        action="workspace.widget.summoned",
        outcome="success",
        email=ctx.email,
        user_id=ctx.user_id,
        details={
            "workspaceId": workspace_id,
            "widgetId": widget["instanceId"],
            "catalogId": widget["catalogId"],
            "source": "ai_agent",
        },
    )


async def _get_workspace(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    store = ctx.workspace_store
    if store is None:
        return {"error": "workspace store not configured"}
    workspace_id = str(args.get("workspaceId") or args.get("workspace_id") or "").strip()
    try:
        if workspace_id:
            payload = _workspace_get(store, workspace_id, owner_user_id=ctx.user_id)
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


async def _summon_widget(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    store = ctx.workspace_store
    if store is None:
        return {"error": "workspace store not configured"}
    draft = args.get("draft") if isinstance(args.get("draft"), dict) else {}
    try:
        workspace_id, workspace = _workspace_for_write(ctx, args)
        widgets = [
            dict(widget)
            for widget in workspace.get("widgets", [])
            if isinstance(widget, dict)
        ]
        provider = str(args.get("provider") or draft.get("provider") or "").strip()
        integration_id = str(
            args.get("integrationId")
            or args.get("integration_id")
            or draft.get("integrationId")
            or draft.get("integration_id")
            or ""
        ).strip()
        bindings = _field_bindings_for_widget(
            args=args,
            draft=draft,
            integration_id=integration_id,
            provider=provider,
        )
        if not integration_id and bindings:
            integration_id = str(bindings[0].get("integrationId") or "")
        widget = {
            "instanceId": str(
                args.get("instanceId")
                or args.get("instance_id")
                or f"w_agent_{token_urlsafe(6)}"
            ),
            "catalogId": _catalog_id_for_widget(args, draft),
            "integrationId": integration_id,
            "layout": _layout_for_widget(args=args, draft=draft, widgets=widgets),
        }
        if bindings:
            widget["fieldBindings"] = bindings
        widgets.append(widget)
        save_response = store.save(
            workspace_id=workspace_id,
            owner_user_id=ctx.user_id,
            name=str(workspace.get("name") or args.get("name") or "SOC Overview"),
            widgets=widgets,
        )
        _record_summon_audit(ctx, workspace_id=workspace_id, widget=widget)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return {
        "workspaceId": workspace_id,
        "widget": widget,
        "widgetCount": len(widgets),
        "save": save_response if isinstance(save_response, dict) else {},
    }


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
        name="summon_widget",
        description=(
            "Persist a dashboard widget into the active cockpit workspace "
            "after human approval. Accepts either a draft_widget response's "
            "draft payload or a catalogId with optional fieldBindings."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workspaceId": {"type": "string"},
                "catalogId": {"type": "string"},
                "integrationId": {"type": "string"},
                "provider": {"type": "string"},
                "visualType": {"type": "string"},
                "instanceId": {"type": "string"},
                "draft": {"type": "object"},
                "fieldBindings": {"type": "array", "items": {"type": "object"}},
                "layout": {"type": "object"},
                "position": {"type": "object"},
            },
            "additionalProperties": False,
        },
        impl=_summon_widget,
        category="write",
        requires_approval=True,
        required_permissions=frozenset({"workspaces.manage"}),
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
