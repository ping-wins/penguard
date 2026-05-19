"""Backend protocol — wire format adapters for Claude / OpenAI / scripted.

Each backend turns the agent's canonical history and filtered tool registry
into an async stream of events. Backends never execute tools; the runner
consumes tool-call events, invokes tools, records results back into history,
and calls the backend again for the next model turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.ai.agent.registry import AgentTool


@dataclass(frozen=True)
class TextDelta:
    kind: Literal["text_delta"] = "text_delta"
    text: str = ""


@dataclass(frozen=True)
class ToolCall:
    kind: Literal["tool_call"] = "tool_call"
    call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Final:
    kind: Literal["final"] = "final"
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence"] | str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(frozen=True)
class BackendError:
    kind: Literal["error"] = "error"
    message: str = ""
    code: Literal["rate_limit", "auth", "transport", "context_overflow", "other"] | str = ""
    retryable: bool = False


BackendStreamEvent = TextDelta | ToolCall | Final | BackendError


class AgentBackend(Protocol):
    name: str
    model: str

    async def stream_decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: list[AgentTool],
        system_prompt: str,
        locale: str,
        max_output_tokens: int,
    ) -> AsyncIterator[BackendStreamEvent]:
        """Yield the model turn for the conversation history.

        `history` is the canonical runner-side form. It includes a system
        entry plus user, assistant, and tool entries. Implementations translate
        it to the provider's native wire format.
        """
        ...
