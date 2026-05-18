"""Shared internal AI tool contracts.

These functions are the stable backend boundary that cockpit chat, LangGraph
triage workflows and a future MCP server should reuse. Model runtimes do not
call service internals directly.
"""

from app.ai.tools.incident_tools import (
    draft_containment_playbook,
    get_incident,
    list_incidents,
    update_incident_status,
)
from app.ai.tools.registry import list_tool_specs
from app.ai.tools.schemas import DraftWidgetRequest, ToolSpec, WidgetDraftResponse
from app.ai.tools.widget_tools import WidgetDraftValidationError, draft_widget, list_data_fields

__all__ = [
    "DraftWidgetRequest",
    "ToolSpec",
    "WidgetDraftResponse",
    "WidgetDraftValidationError",
    "draft_containment_playbook",
    "draft_widget",
    "get_incident",
    "list_data_fields",
    "list_incidents",
    "list_tool_specs",
    "update_incident_status",
]
