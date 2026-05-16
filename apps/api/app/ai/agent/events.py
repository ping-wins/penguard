"""SSE event payloads emitted by the agent runner.

Frontends parse these via the EventSource stream. Shapes are stable; new
event kinds must be additive so older clients can ignore them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class AgentEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class AgentEvent:
    kind: AgentEventType
    step: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass(frozen=True)
class TextDeltaEvent(AgentEvent):
    text: str = ""
    kind: AgentEventType = AgentEventType.TEXT_DELTA


@dataclass(frozen=True)
class ToolCallEvent(AgentEvent):
    call_id: str = field(default_factory=lambda: uuid4().hex)
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    kind: AgentEventType = AgentEventType.TOOL_CALL


@dataclass(frozen=True)
class ToolResultEvent(AgentEvent):
    call_id: str = ""
    tool_name: str = ""
    status: str = "ok"  # ok | error
    result: Any = None
    error: str | None = None
    latency_ms: int = 0
    kind: AgentEventType = AgentEventType.TOOL_RESULT


@dataclass(frozen=True)
class AwaitingApprovalEvent(AgentEvent):
    call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    kind: AgentEventType = AgentEventType.AWAITING_APPROVAL


@dataclass(frozen=True)
class DoneEvent(AgentEvent):
    reply: str = ""
    used_tools: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    kind: AgentEventType = AgentEventType.DONE


@dataclass(frozen=True)
class ErrorEvent(AgentEvent):
    message: str = ""
    code: str = "agent_error"
    kind: AgentEventType = AgentEventType.ERROR
