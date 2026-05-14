import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.store import SiemStore

SERVICE_NAME = "siem_kowalski"
IncidentStatus = Literal["open", "triaged", "contained", "resolved", "false_positive"]
TriageLevel = Literal["T1", "T2", "T3"]
TicketStatus = Literal["new", "investigating", "contained", "closed"]
RuleOperator = Literal["equals", "gte", "exists", "contains"]
RuleMatch = Literal["all", "any"]
logger = logging.getLogger("uvicorn.error")


def _triage_from_severity(severity: str) -> TriageLevel:
    normalized = (severity or "").lower()
    if normalized in {"critical", "high"}:
        return "T1"
    if normalized == "medium":
        return "T2"
    return "T3"

app = FastAPI(title="siem_kowalski", version="0.1.0")
store = SiemStore()


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
    rule_id: str | None = Field(default=None, alias="ruleId")
    title: str
    severity: str
    status: IncidentStatus = "open"
    source: Literal["kowalski"] = "kowalski"
    origin: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    entities: dict[str, Any] = Field(default_factory=dict)
    summary: str
    created_at: datetime = Field(alias="createdAt")
    timeline: list[TimelineItem] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list, alias="eventIds")
    triage_level: TriageLevel = Field(default="T3", alias="triageLevel")
    ticket_status: TicketStatus = Field(default="new", alias="ticketStatus")
    assignee_user_id: str | None = Field(default=None, alias="assigneeUserId")
    ai_analysis_id: str | None = Field(default=None, alias="aiAnalysisId")


class IncidentStatusPatch(BaseModel):
    status: IncidentStatus


class IncidentTriagePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    triage_level: TriageLevel | None = Field(default=None, alias="triageLevel")
    ticket_status: TicketStatus | None = Field(default=None, alias="ticketStatus")
    assignee_user_id: str | None = Field(default=None, alias="assigneeUserId")
    ai_analysis_id: str | None = Field(default=None, alias="aiAnalysisId")
    note: str | None = None


class RuleCondition(BaseModel):
    path: str
    operator: RuleOperator
    value: Any | None = None


class DetectionRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    summary: str
    severity: str | None = None
    event_types: list[str] = Field(default_factory=list, alias="eventTypes")
    match: RuleMatch = "all"
    conditions: list[RuleCondition] = Field(default_factory=list)


DETECTION_RULES: list[DetectionRule] = [
    DetectionRule(
        id="network_scan",
        title="Possible port scan",
        severity="high",
        summary="Network scan telemetry was observed.",
        eventTypes=["network.scan"],
    ),
    DetectionRule(
        id="denied_traffic_burst",
        title="Denied traffic burst",
        summary="Denied network traffic exceeded the configured burst threshold.",
        eventTypes=["network.deny"],
        conditions=[RuleCondition(path="attributes.count", operator="gte", value=20)],
    ),
    DetectionRule(
        id="repeated_failed_login",
        title="Repeated failed login",
        summary="Failed authentication attempts exceeded the configured threshold.",
        eventTypes=["auth.failed_login"],
        conditions=[RuleCondition(path="attributes.count", operator="gte", value=5)],
    ),
    DetectionRule(
        id="privileged_logon_unusual_host",
        title="Privileged logon on unusual host",
        severity="high",
        summary="A privileged account logged on to a host outside the expected baseline.",
        eventTypes=["auth.privileged_logon"],
        conditions=[
            RuleCondition(path="attributes.privileged", operator="equals", value=True),
            RuleCondition(path="attributes.unusualHost", operator="equals", value=True),
        ],
    ),
    DetectionRule(
        id="critical_server_file_change",
        title="Critical server file change",
        severity="high",
        summary="Endpoint telemetry reported a file change under a critical watched path.",
        eventTypes=["file.change"],
        conditions=[RuleCondition(path="attributes.criticalPath", operator="equals", value=True)],
    ),
    DetectionRule(
        id="suspicious_endpoint_connection",
        title="Suspicious endpoint connection",
        severity="high",
        summary="Endpoint telemetry reported a suspicious connection.",
        eventTypes=["endpoint.suspicious_connection"],
    ),
    DetectionRule(
        id="fortigate_resource_pressure",
        title="FortiGate resource pressure",
        severity="high",
        summary="FortiGate system telemetry reported high CPU or memory pressure.",
        eventTypes=["fortigate.system_status"],
        match="any",
        conditions=[
            RuleCondition(path="attributes.cpuPercent", operator="gte", value=90),
            RuleCondition(path="attributes.memoryPercent", operator="gte", value=90),
        ],
    ),
]


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


def _detect_incident(event: SecurityEvent) -> Incident | None:
    event_id = event.id
    if event_id is None:
        return None

    rule = next((rule for rule in DETECTION_RULES if _matches_rule(event, rule)), None)
    if rule is None:
        return None

    incident_severity = rule.severity or event.severity
    return Incident(
        id=_new_id("inc"),
        ruleId=rule.id,
        title=rule.title,
        severity=incident_severity,
        origin={"kind": event.source},
        attributes=_incident_attributes(event),
        entities=event.entities,
        summary=rule.summary,
        createdAt=_now(),
        timeline=[_timeline_item(f"Incident created from event {event_id}.")],
        eventIds=[event_id],
        triageLevel=_triage_from_severity(incident_severity),
        ticketStatus="new",
    )


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True, mode="json")


def _load_event(payload: dict[str, Any]) -> SecurityEvent:
    return SecurityEvent(**payload)


def _load_incident(payload: dict[str, Any]) -> Incident:
    return Incident(**payload)


def _incident_attributes(event: SecurityEvent) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "source": event.attributes.get("source") or event.source,
    }
    for key in (
        "demoRunId",
        "attackType",
        "count",
        "users",
        "attempts",
        "message",
        "action",
        "subtype",
    ):
        value = event.attributes.get(key)
        if value is not None and value != "":
            attributes[key] = value
    return attributes


def _matches_rule(event: SecurityEvent, rule: DetectionRule) -> bool:
    if rule.event_types and event.event_type not in rule.event_types:
        return False
    results = [_matches_condition(event, condition) for condition in rule.conditions]
    if rule.match == "any":
        return any(results)
    return all(results)


def _matches_condition(event: SecurityEvent, condition: RuleCondition) -> bool:
    value = _value_at_path(event, condition.path)
    if condition.operator == "exists":
        return value is not None and value != ""
    if condition.operator == "equals":
        return value == condition.value
    if condition.operator == "contains":
        return _contains(value, condition.value)
    if condition.operator == "gte":
        return _coerce_number(value) >= _coerce_number(condition.value)
    return False


def _value_at_path(event: SecurityEvent, path: str) -> Any:
    if path == "eventType":
        return event.event_type
    if path == "source":
        return event.source
    if path == "severity":
        return event.severity
    if path.startswith("entities."):
        return _dict_path(event.entities, path.removeprefix("entities."))
    if path.startswith("attributes."):
        return _dict_path(event.attributes, path.removeprefix("attributes."))
    return None


def _dict_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _contains(value: Any, expected: Any) -> bool:
    if isinstance(value, str) and isinstance(expected, str):
        return expected in value
    if isinstance(value, list):
        return expected in value
    return False


def _coerce_number(value: Any) -> float:
    if isinstance(value, bool):
        return float("-inf")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return float("-inf")
    return float("-inf")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/rules", response_model=list[DetectionRule])
def list_rules(enabled: bool | None = None) -> list[DetectionRule]:
    logger.info("siem_rules_list enabled=%s returned=%s", enabled, len(DETECTION_RULES))
    return DETECTION_RULES


@app.post("/events", response_model=SecurityEvent)
def create_event(event: SecurityEvent) -> SecurityEvent:
    stored_event = event.model_copy(update={"id": event.id or _new_id("evt")})
    store.add_event(
        _dump(stored_event),
        event_type=stored_event.event_type,
        severity=stored_event.severity,
        occurred_at=stored_event.occurred_at,
    )

    incident = _detect_incident(stored_event)
    if incident is not None:
        store.add_incident(
            _dump(incident),
            rule_id=incident.rule_id,
            severity=incident.severity,
            status=incident.status,
            created_at=incident.created_at,
        )

    logger.info(
        "siem_event_ingested event_id=%s event_type=%s severity=%s incident_created=%s "
        "total_events=%s total_incidents=%s",
        stored_event.id,
        stored_event.event_type,
        stored_event.severity,
        incident is not None,
        store.count_events(),
        store.count_incidents(),
    )
    return stored_event


@app.get("/events", response_model=list[SecurityEvent])
def list_events(
    limit: int | None = Query(default=None, ge=1),
    event_type: str | None = Query(default=None, alias="eventType"),
) -> list[SecurityEvent]:
    payloads = store.list_events(limit=limit, event_type=event_type)
    filtered_events = [_load_event(payload) for payload in payloads]
    logger.info(
        "siem_events_list event_type=%s limit=%s returned=%s total=%s",
        event_type,
        limit,
        len(filtered_events),
        store.count_events(),
    )
    return filtered_events


@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    status: IncidentStatus | None = None,
    severity: str | None = None,
    triage_level: Annotated[TriageLevel | None, Query(alias="triageLevel")] = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="ticketStatus")] = None,
) -> list[Incident]:
    results = [
        _load_incident(payload)
        for payload in store.list_incidents(status=status, severity=severity)
    ]
    if triage_level is not None:
        results = [r for r in results if r.triage_level == triage_level]
    if ticket_status is not None:
        results = [r for r in results if r.ticket_status == ticket_status]
    logger.info(
        "siem_incidents_list status=%s severity=%s triage=%s ticketStatus=%s returned=%s total=%s",
        status,
        severity,
        triage_level,
        ticket_status,
        len(results),
        store.count_incidents(),
    )
    return results


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: str) -> Incident:
    payload = store.get_incident(incident_id)
    if payload is not None:
        return _load_incident(payload)
    raise HTTPException(status_code=404, detail="Incident not found")


@app.patch("/incidents/{incident_id}", response_model=Incident)
def update_incident_status(incident_id: str, patch: IncidentStatusPatch) -> Incident:
    payload = store.get_incident(incident_id)
    if payload is not None:
        incident = _load_incident(payload)
        updated = incident.model_copy(
            update={
                "status": patch.status,
                "timeline": [
                    *incident.timeline,
                    _timeline_item(f"Status changed to {patch.status}.", status=patch.status),
                ],
            }
        )
        store.update_incident(_dump(updated), severity=updated.severity, status=updated.status)
        logger.info(
            "siem_incident_status_updated incident_id=%s status=%s timeline_items=%s",
            incident_id,
            patch.status,
            len(updated.timeline),
        )
        return updated
    raise HTTPException(status_code=404, detail="Incident not found")


@app.patch("/incidents/{incident_id}/triage", response_model=Incident)
def update_incident_triage(incident_id: str, patch: IncidentTriagePatch) -> Incident:
    payload = store.get_incident(incident_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = _load_incident(payload)

    updates: dict[str, Any] = {}
    timeline_notes: list[str] = []
    if patch.triage_level is not None and patch.triage_level != incident.triage_level:
        updates["triage_level"] = patch.triage_level
        timeline_notes.append(
            f"Triage changed from {incident.triage_level} to {patch.triage_level}."
        )
    if patch.ticket_status is not None and patch.ticket_status != incident.ticket_status:
        updates["ticket_status"] = patch.ticket_status
        timeline_notes.append(
            f"Ticket status changed from {incident.ticket_status} to {patch.ticket_status}."
        )
    if patch.assignee_user_id is not None and patch.assignee_user_id != incident.assignee_user_id:
        updates["assignee_user_id"] = patch.assignee_user_id
        timeline_notes.append(f"Assigned to user {patch.assignee_user_id}.")
    if patch.ai_analysis_id is not None and patch.ai_analysis_id != incident.ai_analysis_id:
        updates["ai_analysis_id"] = patch.ai_analysis_id
        timeline_notes.append(f"AI analysis linked: {patch.ai_analysis_id}.")
    if patch.note:
        timeline_notes.append(patch.note)

    if not updates and not timeline_notes:
        return incident

    new_timeline = list(incident.timeline)
    for note in timeline_notes:
        new_timeline.append(_timeline_item(note))
    if new_timeline is not incident.timeline:
        updates["timeline"] = new_timeline

    updated = incident.model_copy(update=updates)
    store.update_incident(_dump(updated), severity=updated.severity, status=updated.status)
    logger.info(
        "siem_incident_triage_updated incident_id=%s triage=%s ticket_status=%s assignee=%s",
        incident_id,
        updated.triage_level,
        updated.ticket_status,
        updated.assignee_user_id,
    )
    return updated
