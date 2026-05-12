from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_MAX_BYTES = 256 * 1024
MANIFEST_MAX_WIDGETS = 200

_SECRET_KEYS = {
    "api_key",
    "apiKey",
    "api_key_blob",
    "apiKeyBlob",
    "secret",
    "client_secret",
    "clientSecret",
    "password",
    "token",
    "access_token",
    "accessToken",
    "refresh_token",
    "refreshToken",
    "keytab",
    "enrollment_token",
    "enrollmentToken",
    "session_id",
    "sessionId",
}


class ManifestWidgetLayout(BaseModel):
    x: int
    y: int
    w: int
    h: int
    z: int


class ManifestFieldBinding(BaseModel):
    field_id: str = Field(alias="fieldId")
    label: str
    type: str
    unit: str | None = None
    source: str
    provider: str | None = None
    group_id: str | None = Field(default=None, alias="groupId")
    group_name: str | None = Field(default=None, alias="groupName")

    model_config = ConfigDict(populate_by_name=True)


class ManifestWidget(BaseModel):
    instance_id: str = Field(alias="instanceId")
    catalog_id: str = Field(alias="catalogId")
    provider_type: str = Field(alias="providerType")
    layout: ManifestWidgetLayout
    field_bindings: list[ManifestFieldBinding] = Field(default_factory=list, alias="fieldBindings")
    title_override: str | None = Field(default=None, alias="titleOverride")
    notes: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class PresentationSlide(BaseModel):
    widget_instance_id: str = Field(alias="widgetInstanceId")
    title: str
    narration: str | None = None
    highlight_field_ids: list[str] = Field(default_factory=list, alias="highlightFieldIds")

    model_config = ConfigDict(populate_by_name=True)


class PresentationMetadata(BaseModel):
    title: str
    incident_summary: str | None = Field(default=None, alias="incidentSummary")
    presenter_name: str | None = Field(default=None, alias="presenterName")
    audience: str | None = None
    severity: str | None = None
    slides: list[PresentationSlide] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ManifestMetadata(BaseModel):
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    incident_id: str | None = Field(default=None, alias="incidentId")
    exported_at: str = Field(alias="exportedAt")
    exported_by_email: str | None = Field(default=None, alias="exportedByEmail")

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceManifest(BaseModel):
    schema_version: int = Field(default=MANIFEST_SCHEMA_VERSION, alias="schemaVersion")
    workspace_id: str = Field(alias="workspaceId")
    name: str
    widgets: list[ManifestWidget] = Field(default_factory=list)
    provider_types: list[str] = Field(default_factory=list, alias="providerTypes")
    presentation: PresentationMetadata | None = None
    metadata: ManifestMetadata

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


def redact_secrets(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("***redacted***" if key in _SECRET_KEYS else redact_secrets(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_secrets(item) for item in payload]
    return payload


def build_manifest(
    *,
    workspace: dict[str, Any],
    exported_by_email: str | None,
    presentation: PresentationMetadata | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    incident_id: str | None = None,
) -> WorkspaceManifest:
    raw_widgets = workspace.get("widgets") or []
    widgets: list[ManifestWidget] = []
    provider_types: set[str] = set()
    for widget in raw_widgets:
        if not isinstance(widget, dict):
            continue
        provider_type = _detect_provider_type(widget)
        provider_types.add(provider_type)
        widgets.append(
            ManifestWidget(
                instanceId=str(widget.get("instanceId") or ""),
                catalogId=str(widget.get("catalogId") or ""),
                providerType=provider_type,
                layout=ManifestWidgetLayout(
                    **widget.get("layout", {"x": 0, "y": 0, "w": 4, "h": 3, "z": 100})
                ),
                fieldBindings=[
                    ManifestFieldBinding(**redact_secrets(binding))
                    for binding in (widget.get("fieldBindings") or [])
                    if isinstance(binding, dict)
                ],
            )
        )
    metadata = ManifestMetadata(
        exportedAt=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        exportedByEmail=exported_by_email,
        description=description,
        tags=list(tags or []),
        incidentId=incident_id,
    )
    return WorkspaceManifest(
        schemaVersion=MANIFEST_SCHEMA_VERSION,
        workspaceId=str(workspace.get("id") or ""),
        name=str(workspace.get("name") or "Untitled"),
        widgets=widgets,
        providerTypes=sorted(provider_types),
        presentation=presentation,
        metadata=metadata,
    )


def manifest_to_widgets(
    manifest: WorkspaceManifest,
    *,
    integration_id_by_provider: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Convert manifest widgets to workspace widgets.

    When ``integration_id_by_provider`` is provided, each widget's
    ``integrationId`` is bound to the recipient's matching integration. Widgets
    without a matching integration fall back to an empty string so the UI can
    prompt the user to reconnect.
    """
    mapping = integration_id_by_provider or {}
    widgets: list[dict[str, Any]] = []
    for widget in manifest.widgets:
        payload = {
            "instanceId": widget.instance_id,
            "catalogId": widget.catalog_id,
            "integrationId": mapping.get(widget.provider_type, ""),
            "layout": widget.layout.model_dump(),
        }
        bindings: list[dict[str, Any]] = []
        for binding in widget.field_bindings:
            binding_payload = binding.model_dump(by_alias=True)
            mapped_integration = mapping.get(widget.provider_type)
            if mapped_integration:
                binding_payload["integrationId"] = mapped_integration
            bindings.append(binding_payload)
        if bindings:
            payload["fieldBindings"] = bindings
        widgets.append(payload)
    return widgets


def validate_manifest_payload(payload: Any) -> WorkspaceManifest:
    if not isinstance(payload, dict):
        raise ValueError("Manifest must be a JSON object")
    schema_version = payload.get("schemaVersion") or payload.get("schema_version")
    if schema_version not in (None, MANIFEST_SCHEMA_VERSION):
        raise ValueError(f"Unsupported manifest schemaVersion={schema_version}")
    sanitized = redact_secrets(payload)
    widgets = sanitized.get("widgets") or []
    if len(widgets) > MANIFEST_MAX_WIDGETS:
        raise ValueError(f"Manifest has {len(widgets)} widgets, max {MANIFEST_MAX_WIDGETS}")
    return WorkspaceManifest.model_validate(sanitized)


def _detect_provider_type(widget: dict[str, Any]) -> str:
    catalog_id = str(widget.get("catalogId") or "")
    integration_id = str(widget.get("integrationId") or "")
    if catalog_id.startswith("fortigate-") or integration_id.startswith("int_fgt_"):
        return "fortigate"
    if catalog_id.startswith("siem-") or "siem" in integration_id:
        return "siem_kowalski"
    if catalog_id.startswith("soar-") or "soar" in integration_id:
        return "soar_skipper"
    if catalog_id.startswith("xdr-") or "xdr" in integration_id:
        return "xdr_rico"
    return "generic"
