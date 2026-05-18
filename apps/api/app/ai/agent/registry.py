"""Tool registry for the SOC agent.

A `AgentTool` is a callable `(ctx, args) -> dict` plus a JSON Schema
description. Backends translate this into their wire format (Anthropic
`tools=`, OpenAI Responses `tools=`, etc).

Tools are *read-only* in PR1. Write tools land in PR4 with the approval
gate; the `requires_approval` flag here is reserved for that future cut.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal


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
    extras: dict[str, Any] = field(default_factory=dict)


ToolImpl = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    impl: ToolImpl
    category: Literal["read", "draft", "write"] = "read"
    requires_approval: bool = False
    timeout_seconds: int = 5


REGISTRY: dict[str, AgentTool] = {}


def register_tool(tool: AgentTool) -> AgentTool:
    if tool.name in REGISTRY:
        raise ValueError(f"Duplicate agent tool: {tool.name}")
    if tool.category not in {"read", "draft", "write"}:
        raise ValueError(f"Unsupported agent tool category: {tool.category}")
    if tool.category == "write" and not tool.requires_approval:
        raise ValueError("write agent tools must set requires_approval=True")
    REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> AgentTool | None:
    return REGISTRY.get(name)


def list_tools() -> list[AgentTool]:
    return list(REGISTRY.values())


def reset_registry_for_tests() -> None:
    REGISTRY.clear()
