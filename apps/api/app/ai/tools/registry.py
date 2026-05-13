from __future__ import annotations

from app.ai.tools.schemas import ToolSpec


def list_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="list_data_fields",
            category="workspace",
            description="List bindable provider fields available to AI drafts.",
            requires_confirmation=False,
            destructive=False,
            timeout_seconds=2,
            input_schema={
                "type": "object",
                "required": ["provider"],
                "properties": {"provider": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "properties": {"groups": {"type": "array"}},
            },
        ),
        ToolSpec(
            name="draft_widget",
            category="workspace",
            description="Create a draft custom widget from provider fields.",
            requires_confirmation=True,
            destructive=False,
            timeout_seconds=3,
            input_schema={
                "type": "object",
                "required": ["provider", "visualType", "fieldIds"],
                "properties": {
                    "provider": {"type": "string"},
                    "integrationId": {"type": "string"},
                    "visualType": {"type": "string"},
                    "fieldIds": {"type": "array", "items": {"type": "string"}},
                    "title": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"const": "draft"},
                    "draft": {"type": "object"},
                    "validation": {"type": "object"},
                },
            },
        ),
        ToolSpec(
            name="validate_widget",
            category="workspace",
            description="Validate a draft widget before workspace insertion.",
            requires_confirmation=False,
            destructive=False,
            timeout_seconds=2,
            input_schema={
                "type": "object",
                "required": ["provider", "visualType", "fieldIds"],
                "properties": {
                    "provider": {"type": "string"},
                    "visualType": {"type": "string"},
                    "fieldIds": {"type": "array", "items": {"type": "string"}},
                },
            },
            output_schema={
                "type": "object",
                "properties": {"valid": {"type": "boolean"}, "errors": {"type": "array"}},
            },
        ),
        ToolSpec(
            name="simulate_widget_data",
            category="workspace",
            description="Generate clearly labeled preview data for a draft widget.",
            requires_confirmation=False,
            destructive=False,
            timeout_seconds=2,
            input_schema={
                "type": "object",
                "required": ["provider", "fieldIds"],
                "properties": {
                    "provider": {"type": "string"},
                    "fieldIds": {"type": "array", "items": {"type": "string"}},
                },
            },
            output_schema={
                "type": "object",
                "properties": {"source": {"const": "simulation"}, "values": {"type": "object"}},
            },
        ),
        ToolSpec(
            name="draft_containment_playbook",
            category="soc",
            description="Draft a SOAR-compatible containment playbook for a ticket.",
            requires_confirmation=True,
            destructive=False,
            timeout_seconds=10,
            input_schema={
                "type": "object",
                "required": ["ticketId"],
                "properties": {"ticketId": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "properties": {"playbook": {"type": "object"}, "simulation": {"type": "object"}},
            },
        ),
    ]
