"""Backend protocol — wire format adapters for Claude / OpenAI / scripted.

Each backend turns the agent's message history + tool registry into a
sequence of `BackendDecision` instances: either call a tool or finish
with a final text reply. The runner handles the tool invocation, audit
logging, and SSE emission.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.agent.registry import AgentTool


@dataclass(frozen=True)
class BackendDecision:
    """One step the backend wants to take.

    kind="tool_call" means: invoke `tool_name` with `args`. After the
    runner executes it and records the result back into history, the
    backend is called again for the next decision.

    kind="final" means: agent is done, emit `text` as the final reply.
    """

    kind: str  # "tool_call" | "final"
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


class AgentBackend(Protocol):
    name: str
    model: str

    def decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: Iterable[AgentTool],
        locale: str,
    ) -> BackendDecision:
        """Return the next step given the conversation history.

        `history` is a flat list of dicts; entries with role="user" and
        role="assistant" carry text, role="tool" carries the JSON result
        of a previous tool call (with tool_call_id+tool_name+result).
        """
        ...
