from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

SERVICE_NAME = "siem_kowalski"
IncidentStatus = Literal["open", "triaged", "contained", "resolved", "false_positive"]

app = FastAPI(title="siem_kowalski", version="0.1.0")

events: list["SecurityEvent"] = []
incidents: list["Incident"] = []


class SecurityEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    source: str
    event_type: str = Field(alias="eventType")
    severity: str
    occurred_at: datetime = Field(alias="occurredAt")
    entities: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TimelineItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    status: IncidentStatus | None = None
    message: str
    occurred_at: datetime = Field(alias="occurredAt")


class Incident(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    severity: str
    status: IncidentStatus = "open"
    source: Literal["kowalski"] = "kowalski"
    entities: dict[str, Any] = Field(default_factory=dict)
    summary: str
    created_at: datetime = Field(alias="createdAt")
    timeline: list[TimelineItem] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list, alias="eventIds")


class IncidentStatusPatch(BaseModel):
    status: IncidentStatus


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _timeline_item(message: str, *, status: IncidentStatus | None = None) -> TimelineItem:
    return TimelineItem(
        id=_new_id("tl"),
        type="status_change" if status is not None else "created",
        status=status,
        message=message,
        occurredAt=_now(),
    )


def _count_attribute(event: SecurityEvent) -> int:
    count = event.attributes.get("count", 0)
    if isinstance(count, bool):
        return 0
    if isinstance(count, int | float):
        return int(count)
    if isinstance(count, str) and count.isdigit():
        return int(count)
    return 0


def _detect_incident(event: SecurityEvent) -> Incident | None:
    event_id = event.id
    if event_id is None:
        return None

    title: str
    severity: str
    summary: str

    if event.event_type == "network.scan":
        title = "Possible port scan"
        severity = "high"
        summary = "Network scan telemetry was observed."
    elif event.event_type == "network.deny" and _count_attribute(event) >= 20:
        title = "Denied traffic burst"
        severity = event.severity
        summary = "Denied network traffic exceeded the configured burst threshold."
    elif event.event_type == "auth.failed_login" and _count_attribute(event) >= 5:
        title = "Repeated failed login"
        severity = event.severity
        summary = "Failed authentication attempts exceeded the configured threshold."
    elif event.event_type == "endpoint.suspicious_connection":
        title = "Suspicious endpoint connection"
        severity = "high"
        summary = "Endpoint telemetry reported a suspicious connection."
    else:
        return None

    return Incident(
        id=_new_id("inc"),
        title=title,
        severity=severity,
        entities=event.entities,
        summary=summary,
        createdAt=_now(),
        timeline=[_timeline_item(f"Incident created from event {event_id}.")],
        eventIds=[event_id],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/events", response_model=SecurityEvent)
def create_event(event: SecurityEvent) -> SecurityEvent:
    stored_event = event.model_copy(update={"id": event.id or _new_id("evt")})
    events.append(stored_event)

    incident = _detect_incident(stored_event)
    if incident is not None:
        incidents.append(incident)

    return stored_event


@app.get("/events", response_model=list[SecurityEvent])
def list_events(
    limit: int | None = Query(default=None, ge=1),
    event_type: str | None = Query(default=None, alias="eventType"),
) -> list[SecurityEvent]:
    filtered_events = [
        event for event in reversed(events) if event_type is None or event.event_type == event_type
    ]
    if limit is not None:
        return filtered_events[:limit]
    return filtered_events


@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    status: IncidentStatus | None = None,
    severity: str | None = None,
) -> list[Incident]:
    return [
        incident
        for incident in reversed(incidents)
        if (status is None or incident.status == status)
        and (severity is None or incident.severity == severity)
    ]


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: str) -> Incident:
    for incident in incidents:
        if incident.id == incident_id:
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")


@app.patch("/incidents/{incident_id}", response_model=Incident)
def update_incident_status(incident_id: str, patch: IncidentStatusPatch) -> Incident:
    for index, incident in enumerate(incidents):
        if incident.id == incident_id:
            updated = incident.model_copy(
                update={
                    "status": patch.status,
                    "timeline": [
                        *incident.timeline,
                        _timeline_item(f"Status changed to {patch.status}.", status=patch.status),
                    ],
                }
            )
            incidents[index] = updated
            return updated
    raise HTTPException(status_code=404, detail="Incident not found")
