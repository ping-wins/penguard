"""Shared internal AI tool contracts.

These functions are the stable backend boundary that cockpit chat, LangGraph
triage workflows and a future MCP server should reuse. Model runtimes do not
call service internals directly.
"""

from app.ai.tools.registry import list_tool_specs
from app.ai.tools.schemas import DraftWidgetRequest, ToolSpec, WidgetDraftResponse
from app.ai.tools.widget_tools import WidgetDraftValidationError, draft_widget, list_data_fields

__all__ = [
    "DraftWidgetRequest",
    "ToolSpec",
    "WidgetDraftResponse",
    "WidgetDraftValidationError",
    "draft_widget",
    "list_data_fields",
    "list_tool_specs",
]
