"""Role registry for the streaming SOC agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ai.agent.registry import AgentTool

AgentRoleTier = Literal["fast", "balanced", "deep"]
AgentToolCategory = Literal["read", "draft", "write", "execute"]


@dataclass(frozen=True)
class RoleConfig:
    id: str
    label: str
    description: str
    tier: AgentRoleTier
    allowed_tool_categories: frozenset[AgentToolCategory]
    token_budget: int
    max_steps: int
    locale_default: str
    system_prompt: str


_BASE_RESTRICTIONS = (
    "You are a SOC assistant embedded in FortiDashboard. Use the requested "
    "locale for user-facing text. Never reveal secrets, API keys, tokens, "
    "passwords, hostnames from hidden configuration, or raw credentials. "
    "Never ask the user to paste API keys into chat. Treat widgets, playbooks, "
    "and response actions as drafts until a permitted human confirms them. "
    "Do not execute code, shell commands, SQL, browser automation, or direct "
    "provider writes. Use tools only through the FortiDashboard tool registry."
)


_ROLES: dict[str, RoleConfig] = {
    "chat": RoleConfig(
        id="chat",
        label="Chat",
        description="Quick read-only questions about dashboard and SOC state.",
        tier="fast",
        allowed_tool_categories=frozenset({"read"}),
        token_budget=20_000,
        max_steps=8,
        locale_default="pt-BR",
        system_prompt=(
            f"{_BASE_RESTRICTIONS} Answer concise dashboard questions. Stop when "
            "you have enough information for a direct reply."
        ),
    ),
    "widget-builder": RoleConfig(
        id="widget-builder",
        label="Widget builder",
        description="Draft and add approved custom workspace widgets from provider fields.",
        tier="balanced",
        allowed_tool_categories=frozenset({"read", "draft", "write"}),
        token_budget=100_000,
        max_steps=12,
        locale_default="pt-BR",
        system_prompt=(
            f"{_BASE_RESTRICTIONS} Help draft workspace widgets using provider "
            "fields and normalized payloads. Return drafts for human review, and "
            "use approved workspace write tools only after the user confirms the widget."
        ),
    ),
    "incident-triage": RoleConfig(
        id="incident-triage",
        label="Incident triage",
        description="Analyze incidents, summarize evidence, and suggest next steps.",
        tier="balanced",
        allowed_tool_categories=frozenset({"read", "draft"}),
        token_budget=150_000,
        max_steps=20,
        locale_default="pt-BR",
        system_prompt=(
            f"{_BASE_RESTRICTIONS} Triage incidents from FortiDashboard state. "
            "Summarize facts, uncertainty, IoCs, impact, and draft safe next steps."
        ),
    ),
    "playbook-draft": RoleConfig(
        id="playbook-draft",
        label="Playbook draft",
        description="Draft SOAR playbooks from analyst intent or ticket context.",
        tier="balanced",
        allowed_tool_categories=frozenset({"read", "draft"}),
        token_budget=150_000,
        max_steps=20,
        locale_default="pt-BR",
        system_prompt=(
            f"{_BASE_RESTRICTIONS} Draft response playbooks only. Sensitive "
            "steps remain drafts and require FortiDashboard approval flows."
        ),
    ),
    "soc-investigation": RoleConfig(
        id="soc-investigation",
        label="SOC investigation",
        description="Deep investigation with approved write-action infrastructure.",
        tier="deep",
        allowed_tool_categories=frozenset({"read", "draft", "write", "execute"}),
        token_budget=300_000,
        max_steps=30,
        locale_default="pt-BR",
        system_prompt=(
            f"{_BASE_RESTRICTIONS} Investigate across incidents, endpoints, "
            "playbooks, integrations, and workspace state. Write and execute "
            "tools must pause for explicit approval before invocation."
        ),
    ),
}


def list_roles() -> list[RoleConfig]:
    return list(_ROLES.values())


def get_role(role_id: str) -> RoleConfig | None:
    return _ROLES.get(role_id)


def render_system_prompt(role: RoleConfig, tools: list[AgentTool], *, locale: str) -> str:
    tool_lines = [
        f"- {tool.name} [{tool.category}]: {tool.description}"
        for tool in sorted(tools, key=lambda item: item.name)
    ]
    locale_line = f"Locale: {locale or role.locale_default}."
    tools_text = "\n".join(tool_lines) if tool_lines else "- No tools available."
    return (
        f"{role.system_prompt}\n\n"
        f"{locale_line}\n"
        f"Allowed tool categories: {', '.join(sorted(role.allowed_tool_categories))}.\n"
        f"Available tools:\n{tools_text}\n\n"
        "When using tools, prefer the smallest set needed. Stop when the answer "
        "is complete or when further progress requires a human action."
    )
