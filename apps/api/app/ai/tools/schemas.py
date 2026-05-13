from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    category: str
    description: str
    requires_confirmation: bool = Field(alias="requiresConfirmation")
    destructive: bool
    timeout_seconds: int = Field(alias="timeoutSeconds")
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(alias="outputSchema")


class DraftWidgetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field(min_length=1)
    integration_id: str | None = Field(default=None, alias="integrationId")
    visual_type: str = Field(alias="visualType", min_length=1)
    field_ids: list[str] = Field(alias="fieldIds", min_length=1, max_length=12)
    title: str | None = Field(default=None, max_length=120)


class WidgetFieldBinding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    field_id: str = Field(alias="fieldId")
    label: str
    type: str
    unit: str | None = None
    source: str | None = None
    provider: str
    integration_id: str | None = Field(default=None, alias="integrationId")


class WidgetDraft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["draft"] = "draft"
    provider: str
    integration_id: str | None = Field(default=None, alias="integrationId")
    visual_type: str = Field(alias="visualType")
    title: str
    field_bindings: list[WidgetFieldBinding] = Field(alias="fieldBindings")
    layout: dict[str, int]
    settings: dict[str, Any]


class WidgetDraftValidation(BaseModel):
    valid: bool
    warnings: list[str]
    errors: list[str]


class WidgetDraftPreview(BaseModel):
    source: Literal["simulation"] = "simulation"
    values: dict[str, Any]


class WidgetDraftResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tool_name: Literal["draft_widget"] = Field(default="draft_widget", alias="toolName")
    status: Literal["draft"] = "draft"
    requires_confirmation: bool = Field(default=True, alias="requiresConfirmation")
    draft: WidgetDraft
    preview: WidgetDraftPreview
    validation: WidgetDraftValidation
