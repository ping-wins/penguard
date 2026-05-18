"""Autonomous SOC agent runtime.

Separate from `app.ai.cockpit_agent`, which serves the single-turn chat
sidebar. This package hosts the multi-step tool-use agent with pluggable
backends (scripted now, Anthropic + OpenAI in follow-up PRs).
"""

from app.ai.agent.events import (
    AgentEvent,
    AgentEventType,
    AwaitingApprovalEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.ai.agent.registry import (
    REGISTRY,
    AgentTool,
    ToolContext,
    get_tool,
    list_tools,
)
from app.ai.agent.roles import RoleConfig, get_role, list_roles
from app.ai.agent.session import AgentSession, SessionStore, get_session_store

__all__ = [
    "REGISTRY",
    "AgentEvent",
    "AgentEventType",
    "AgentSession",
    "AgentTool",
    "AwaitingApprovalEvent",
    "DoneEvent",
    "ErrorEvent",
    "RoleConfig",
    "SessionStore",
    "TextDeltaEvent",
    "ToolCallEvent",
    "ToolContext",
    "ToolResultEvent",
    "get_role",
    "get_session_store",
    "get_tool",
    "list_roles",
    "list_tools",
]
