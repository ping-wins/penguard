from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool


def _soar_client(ctx: ToolContext):
    if ctx.soar_client is None:
        raise RuntimeError("soar client not configured")
    return ctx.soar_client


def _playbook_from_args(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("playbook")
    source = raw if isinstance(raw, dict) else args
    nodes = source.get("nodes") if isinstance(source.get("nodes"), list) else []
    edges = source.get("edges") if isinstance(source.get("edges"), list) else []
    payload: dict[str, Any] = {
        "schemaVersion": int(source.get("schemaVersion") or source.get("schema_version") or 1),
        "id": str(source.get("id") or source.get("playbookId") or "").strip(),
        "name": str(source.get("name") or "").strip(),
        "enabled": bool(source.get("enabled") or False),
        "nodes": [node for node in nodes if isinstance(node, dict)],
        "edges": [edge for edge in edges if isinstance(edge, dict)],
        "runtimePolicy": (
            source.get("runtimePolicy")
            if isinstance(source.get("runtimePolicy"), dict)
            else source.get("runtime_policy")
            if isinstance(source.get("runtime_policy"), dict)
            else {}
        ),
    }
    return payload


def _node_type_catalog(client: Any) -> dict[str, dict[str, Any]]:
    payload = client.request("GET", "/node-types")
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }


def _edge_from(edge: dict[str, Any]) -> str:
    return str(edge.get("from") or edge.get("from_node") or edge.get("fromNode") or "")


def _edge_to(edge: dict[str, Any]) -> str:
    return str(edge.get("to") or edge.get("to_node") or edge.get("toNode") or "")


def _required_config_fields(node_type: dict[str, Any]) -> list[str]:
    schema = node_type.get("configSchema") or node_type.get("config_schema") or {}
    required = schema.get("required") if isinstance(schema, dict) else []
    return [str(field) for field in required] if isinstance(required, list) else []


def _validate_playbook_payload(
    payload: dict[str, Any],
    *,
    node_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    playbook_id = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []

    if not playbook_id:
        errors.append("playbook id is required")
    if not name:
        errors.append("playbook name is required")
    if not nodes:
        errors.append("playbook must include at least one node")

    node_ids: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        if not node_id:
            errors.append("playbook node id is required")
            continue
        node_ids.append(node_id)
        if not node_type:
            errors.append(f"node {node_id} type is required")
            continue
        if node_types and node_type not in node_types:
            errors.append(f"node {node_id} uses unknown node type: {node_type}")
            continue
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        for field_name in _required_config_fields(node_types.get(node_type, {})):
            field_value = config.get(field_name)
            if field_value is None or field_value == "" or field_value == []:
                errors.append(f"node {node_id} missing required config: {field_name}")

    if len(set(node_ids)) != len(node_ids):
        errors.append("playbook node ids must be unique")
    node_id_set = set(node_ids)
    if nodes and not any(str(node.get("type") or "").startswith("trigger.") for node in nodes):
        errors.append("playbook must include at least one trigger node")
    for edge in edges:
        from_node = _edge_from(edge)
        to_node = _edge_to(edge)
        if from_node not in node_id_set or to_node not in node_id_set:
            errors.append("playbook edges must reference existing node ids")

    return {"valid": not errors, "errors": errors}


def _validation_for(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    client = _soar_client(ctx)
    return _validate_playbook_payload(payload, node_types=_node_type_catalog(client))


async def _list_playbook_node_types(ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = _soar_client(ctx).request("GET", "/node-types")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "items": []}
    if isinstance(payload, dict):
        return payload
    return {"items": payload if isinstance(payload, list) else []}


async def _get_playbook(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    playbook_id = str(args.get("playbookId") or args.get("playbook_id") or "").strip()
    if not playbook_id:
        return {"error": "playbookId is required"}
    try:
        payload = _soar_client(ctx).request("GET", f"/playbooks/{playbook_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "playbookId": playbook_id}
    return payload if isinstance(payload, dict) else {"error": "soar returned non-dict playbook"}


async def _draft_playbook_graph(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        playbook = _playbook_from_args(args)
        playbook["enabled"] = False
        validation = _validation_for(ctx, playbook)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return {"playbook": playbook, "validation": validation}


async def _validate_playbook_graph(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return _validation_for(ctx, _playbook_from_args(args))
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [str(exc)[:200]]}


async def _apply_playbook_patch(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    mode = str(args.get("mode") or "update").strip().lower()
    if mode not in {"create", "update"}:
        return {"error": "mode must be create or update"}
    try:
        client = _soar_client(ctx)
        playbook = _playbook_from_args(args)
        if mode == "create":
            playbook["enabled"] = False
        elif playbook.get("enabled") is True:
            return {"error": "enabling playbooks requires a separate confirmation"}
        validation = _validate_playbook_payload(
            playbook,
            node_types=_node_type_catalog(client),
        )
        if not validation["valid"]:
            return {"error": "validation failed", "validation": validation}
        playbook_id = str(args.get("playbookId") or playbook.get("id") or "").strip()
        if not playbook_id:
            return {"error": "playbookId is required"}
        if mode == "create":
            response = client.request("POST", "/playbooks", json=playbook)
        else:
            response = client.request("PUT", f"/playbooks/{playbook_id}", json=playbook)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return {
        "operation": mode,
        "playbook": response if isinstance(response, dict) else playbook,
        "summary": {
            "playbookId": playbook_id,
            "nodes": len(playbook["nodes"]),
            "edges": len(playbook["edges"]),
            "enabled": bool(playbook.get("enabled")),
        },
    }


async def _simulate_playbook(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    playbook_id = str(args.get("playbookId") or args.get("playbook_id") or "").strip()
    if not playbook_id:
        return {"error": "playbookId is required"}
    try:
        payload = _soar_client(ctx).request(
            "POST",
            f"/playbooks/{playbook_id}/simulate",
            json={},
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "playbookId": playbook_id}
    return payload if isinstance(payload, dict) else {"error": "soar returned non-dict simulation"}


_PLAYBOOK_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "nodes"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "enabled": {"type": "boolean"},
        "nodes": {"type": "array", "items": {"type": "object"}},
        "edges": {"type": "array", "items": {"type": "object"}},
        "runtimePolicy": {"type": "object"},
    },
    "additionalProperties": True,
}


register_tool(
    AgentTool(
        name="list_playbook_node_types",
        description="List available SOAR playbook node types and config schemas.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        impl=_list_playbook_node_types,
    )
)


register_tool(
    AgentTool(
        name="get_playbook",
        description="Read a saved SOAR playbook graph by id.",
        input_schema={
            "type": "object",
            "required": ["playbookId"],
            "properties": {"playbookId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_get_playbook,
    )
)


register_tool(
    AgentTool(
        name="draft_playbook_graph",
        description=(
            "Draft a SOAR playbook graph using existing node ids, edges and "
            "config schemas. Returns validation errors and never persists."
        ),
        input_schema=_PLAYBOOK_SCHEMA,
        impl=_draft_playbook_graph,
        category="draft",
        required_permissions=frozenset({"playbooks.manage"}),
    )
)


register_tool(
    AgentTool(
        name="validate_playbook_graph",
        description="Validate a drafted SOAR playbook graph without persisting it.",
        input_schema={
            "type": "object",
            "required": ["playbook"],
            "properties": {"playbook": _PLAYBOOK_SCHEMA},
            "additionalProperties": False,
        },
        impl=_validate_playbook_graph,
        category="draft",
        required_permissions=frozenset({"playbooks.manage"}),
    )
)


register_tool(
    AgentTool(
        name="apply_playbook_patch",
        description=(
            "Create or update a SOAR playbook graph after user approval. New "
            "playbooks are forced to enabled=false."
        ),
        input_schema={
            "type": "object",
            "required": ["mode", "playbook"],
            "properties": {
                "mode": {"type": "string", "enum": ["create", "update"]},
                "playbookId": {"type": "string"},
                "playbook": _PLAYBOOK_SCHEMA,
            },
            "additionalProperties": False,
        },
        impl=_apply_playbook_patch,
        category="write",
        requires_approval=True,
        required_permissions=frozenset({"playbooks.manage"}),
    )
)


register_tool(
    AgentTool(
        name="simulate_playbook",
        description="Run a dry-run simulation for a saved SOAR playbook.",
        input_schema={
            "type": "object",
            "required": ["playbookId"],
            "properties": {"playbookId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_simulate_playbook,
        category="draft",
        required_permissions=frozenset({"playbooks.execute"}),
    )
)
