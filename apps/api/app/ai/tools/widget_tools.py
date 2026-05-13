from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.ai.tools.schemas import (
    DraftWidgetRequest,
    WidgetDraft,
    WidgetDraftPreview,
    WidgetDraftResponse,
    WidgetDraftValidation,
    WidgetFieldBinding,
)
from app.core.fixtures import load_fixture

PROVIDER_DATA_FIELD_FIXTURES = {
    "fortigate": "data-fields",
    "siem_kowalski": "data_fields_siem_kowalski",
    "xdr_rico": "data_fields_xdr_rico",
    "soar_skipper": "data_fields_soar_skipper",
}

VISUAL_DEFAULTS: dict[str, dict[str, Any]] = {
    "card": {"layout": {"w": 2, "h": 2}, "settings": {"aggregation": "latest"}},
    "kpi": {"layout": {"w": 2, "h": 2}, "settings": {"aggregation": "latest"}},
    "gauge": {"layout": {"w": 3, "h": 2}, "settings": {"aggregation": "latest"}},
    "bar": {"layout": {"w": 4, "h": 3}, "settings": {"aggregation": "latest"}},
    "table": {"layout": {"w": 5, "h": 4}, "settings": {"pageSize": 10}},
    "feed": {"layout": {"w": 5, "h": 4}, "settings": {"pageSize": 10}},
    "status-list": {"layout": {"w": 4, "h": 3}, "settings": {"aggregation": "latest"}},
    "risk-summary": {"layout": {"w": 3, "h": 3}, "settings": {"aggregation": "latest"}},
}


class WidgetDraftValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def draft_widget(request: DraftWidgetRequest) -> WidgetDraftResponse:
    field_map = _field_map_for_provider(request.provider)
    errors = _validate_widget_request(request, field_map)
    if errors:
        raise WidgetDraftValidationError(errors)

    fields = [field_map[field_id] for field_id in request.field_ids]
    visual_defaults = VISUAL_DEFAULTS[request.visual_type]
    bindings = [
        WidgetFieldBinding(
            field_id=field["id"],
            label=field["label"],
            type=field["type"],
            unit=field.get("unit"),
            source=field.get("source"),
            provider=request.provider,
            integration_id=request.integration_id,
        )
        for field in fields
    ]
    warnings = _visual_warnings(request.visual_type, fields)
    title = request.title or _default_title(request.visual_type, fields)
    return WidgetDraftResponse(
        draft=WidgetDraft(
            provider=request.provider,
            integration_id=request.integration_id,
            visual_type=request.visual_type,
            title=title,
            field_bindings=bindings,
            layout=deepcopy(visual_defaults["layout"]),
            settings=deepcopy(visual_defaults["settings"]),
        ),
        preview=WidgetDraftPreview(
            values={field["id"]: _sample_value(field) for field in fields},
        ),
        validation=WidgetDraftValidation(
            valid=True,
            warnings=warnings,
            errors=[],
        ),
    )


def list_data_fields(provider: str) -> dict[str, Any]:
    return _provider_fields_payload(provider)


def _validate_widget_request(
    request: DraftWidgetRequest,
    field_map: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if request.visual_type not in VISUAL_DEFAULTS:
        errors.append(f"Unsupported visual type: {request.visual_type}")
    for field_id in request.field_ids:
        if field_id not in field_map:
            errors.append(f"Unknown provider field: {field_id}")
    return errors


def _visual_warnings(visual_type: str, fields: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for field in fields:
        recommended = set(field.get("recommendedVisuals") or [])
        if visual_type == "card" and "kpi" in recommended:
            continue
        if recommended and visual_type not in recommended:
            warnings.append(
                f"Field {field['id']} does not list {visual_type} as a recommended visual"
            )
    return warnings


def _field_map_for_provider(provider: str) -> dict[str, dict[str, Any]]:
    payload = _provider_fields_payload(provider)
    fields: dict[str, dict[str, Any]] = {}
    for group in payload["groups"]:
        for field in group.get("fields", []):
            fields[field["id"]] = field
    return fields


def _provider_fields_payload(provider: str) -> dict[str, Any]:
    if provider == "soc":
        groups = []
        for source_provider in ("siem_kowalski", "xdr_rico", "soar_skipper"):
            payload = _provider_fields_payload(source_provider)
            for group in payload["groups"]:
                next_group = deepcopy(group)
                next_group["id"] = f"{source_provider}.{next_group['id']}"
                groups.append(next_group)
        return {"provider": "soc", "groups": groups}
    if provider not in PROVIDER_DATA_FIELD_FIXTURES:
        raise WidgetDraftValidationError([f"Unknown provider: {provider}"])
    return load_fixture(PROVIDER_DATA_FIELD_FIXTURES[provider])


def _sample_value(field: dict[str, Any]) -> Any:
    field_type = field.get("type")
    unit = field.get("unit")
    if field_type == "number":
        return 0
    if field_type == "datetime":
        return "2026-01-01T00:00:00.000Z"
    if field_type == "boolean":
        return False
    if unit == "count":
        return 0
    return "sample"


def _default_title(visual_type: str, fields: list[dict[str, Any]]) -> str:
    if len(fields) == 1:
        return fields[0]["label"]
    labels = ", ".join(field["label"] for field in fields[:2])
    return f"{visual_type.replace('-', ' ').title()}: {labels}"
