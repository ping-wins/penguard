"""Tool registry for the SOC agent.

A `AgentTool` is a callable `(ctx, args) -> dict` plus a JSON Schema
description. Backends translate this into their wire format (Anthropic
`tools=`, OpenAI Responses `tools=`, etc).

Read and draft tools may run directly when the role and RBAC allow them.
Write and execute tools must always pause on the approval gate before they
touch SOC state.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.auth.permissions import VALID_PERMISSION_SLUGS, WILDCARD


@dataclass
class ToolContext:
    """Per-request services accessible to tools.

    Built by the router from FastAPI dependencies. Tools never import
    services directly so they stay test-friendly (the test harness can
    inject mocks here without monkey-patching).
    """

    user_id: str
    email: str | None = None
    locale: str = "pt-BR"
    siem_client: Any = None
    soar_client: Any = None
    xdr_client: Any = None
    fortigate_widget_service: Any = None
    fortigate_integration_service: Any = None
    workspace_store: Any = None
    audit_store: Any = None
    effective_permissions: frozenset[str] = field(default_factory=frozenset)
    extras: dict[str, Any] = field(default_factory=dict)


ToolImpl = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    impl: ToolImpl
    category: Literal["read", "draft", "write", "execute"] = "read"
    requires_approval: bool = False
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: int = 5


REGISTRY: dict[str, AgentTool] = {}


def register_tool(tool: AgentTool) -> AgentTool:
    if tool.name in REGISTRY:
        raise ValueError(f"Duplicate agent tool: {tool.name}")
    if tool.category not in {"read", "draft", "write", "execute"}:
        raise ValueError(f"Unsupported agent tool category: {tool.category}")
    if tool.category in {"write", "execute"} and not tool.requires_approval:
        raise ValueError(
            f"{tool.category} agent tools must set requires_approval=True"
        )
    unknown_permissions = sorted(
        permission
        for permission in tool.required_permissions
        if permission != WILDCARD and permission not in VALID_PERMISSION_SLUGS
    )
    if unknown_permissions:
        raise ValueError(f"Unknown permission slug: {unknown_permissions[0]}")
    REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> AgentTool | None:
    return REGISTRY.get(name)


def list_tools() -> list[AgentTool]:
    return list(REGISTRY.values())


def missing_required_permissions(
    tool: AgentTool,
    effective_permissions: frozenset[str],
) -> list[str]:
    """Return tool permission slugs not granted to this request context."""

    if not tool.required_permissions or WILDCARD in effective_permissions:
        return []
    return sorted(tool.required_permissions - effective_permissions)


def tool_allowed_by_permissions(
    tool: AgentTool,
    effective_permissions: frozenset[str],
) -> bool:
    return not missing_required_permissions(tool, effective_permissions)


def reset_registry_for_tests() -> None:
    REGISTRY.clear()
