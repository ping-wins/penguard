import logging
from datetime import UTC, datetime, timedelta
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
ALLOWED_SCAN_WINDOW_SECONDS = 60
ALLOWED_SCAN_MIN_UNIQUE_PORTS = 20
ALLOWED_SCAN_EVENT_LIMIT = 250
HTTP_FLOOD_WINDOW_SECONDS = 60
HTTP_FLOOD_MIN_EVENTS = 100
HTTP_FLOOD_EVENT_LIMIT = 500
HTTP_FLOOD_SUPPRESSION_SECONDS = 300
FORWARDED_SCAN_ACTIONS = {
    "accept",
    "allow",
    "allowed",
    "close",
    "client-rst",
    "server-rst",
    "timeout",
}
HTTP_FLOOD_SERVICES = {"HTTP", "HTTPS"}
HTTP_FLOOD_PORTS = {80, 443, 8080, 8443}


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


class EventIngestResult(BaseModel):
    event: SecurityEvent
    incident: Incident | None = None


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
        title="Possible authentication brute force",
        summary="Failed authentication attempts reached the brute-force threshold.",
        eventTypes=["auth.failed_login"],
        conditions=[RuleCondition(path="attributes.count", operator="gte", value=3)],
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
    DetectionRule(
        id="fortiweb_waf_attack",
        title="FortiWeb WAF attack blocked",
        severity="high",
        summary="FortiWeb blocked a web attack against a protected application.",
        eventTypes=["waf.attack", "http.attack"],
        conditions=[RuleCondition(path="attributes.action", operator="exists")],
    ),
    DetectionRule(
        id="fortiweb_dos_activity",
        title="FortiWeb DoS activity detected",
        severity="critical",
        summary=(
            "FortiDashboard observed or inferred DoS activity against a protected application."
        ),
        eventTypes=["waf.dos"],
    ),
    DetectionRule(
        id="fortiweb_blocked_request",
        title="FortiWeb blocked suspicious request",
        severity="medium",
        summary="FortiWeb blocked a suspicious request against a protected application.",
        eventTypes=["waf.blocked_request"],
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
        attributes=_incident_attributes(event, rule),
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


def _incident_attributes(event: SecurityEvent, rule: DetectionRule) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "source": event.attributes.get("source") or event.source,
        "detection": {
            "ruleId": rule.id,
            "title": rule.title,
            "summary": rule.summary,
            "matchedEventType": event.event_type,
            "observedCount": event.attributes.get("count"),
            "thresholds": [
                {
                    "path": condition.path,
                    "operator": condition.operator,
                    "value": condition.value,
                }
                for condition in rule.conditions
                if condition.operator == "gte"
            ],
        },
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
        "policy",
        "method",
        "url",
        "rawType",
        "rawSubtype",
        "ingestionMode",
        "integrationId",
        "sourceIp",
        "destinationIp",
        "destinationPort",
        "destinationPorts",
        "uniqueDestinationPortCount",
        "scanWindowSeconds",
        "policyId",
        "service",
        "relatedEventIds",
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


def _coerce_int(value: Any) -> int | None:
    numeric = _coerce_number(value)
    if numeric == float("-inf"):
        return None
    return int(numeric)


def _enrich_failed_login_burst(event: SecurityEvent) -> SecurityEvent:
    if event.event_type != "auth.failed_login":
        return event
    current_count = _failed_login_event_count(event)
    if current_count >= 3:
        return _mark_brute_force(event, current_count, [])

    window_start = event.occurred_at - timedelta(minutes=5)
    matched_event_ids: list[str] = []
    total_count = current_count
    for payload in store.list_events(limit=50, event_type="auth.failed_login"):
        previous = _load_event(payload)
        if previous.occurred_at < window_start or previous.occurred_at > event.occurred_at:
            continue
        if not _same_auth_subject(event, previous):
            continue
        previous_count = _failed_login_event_count(previous)
        total_count += previous_count
        if previous.id:
            matched_event_ids.append(previous.id)
        if total_count >= 3:
            break
    if total_count < 3:
        return event
    return _mark_brute_force(event, total_count, matched_event_ids)


def _same_auth_subject(left: SecurityEvent, right: SecurityEvent) -> bool:
    for key in ("integrationId", "sourceIp", "user", "deviceName"):
        left_value = left.entities.get(key) or left.attributes.get(key)
        right_value = right.entities.get(key) or right.attributes.get(key)
        if left_value and right_value and left_value != right_value:
            return False
    return True


def _failed_login_event_count(event: SecurityEvent) -> int:
    numeric = _coerce_number(event.attributes.get("count"))
    if numeric == float("-inf") or numeric < 1:
        return 1
    return int(numeric)


def _mark_brute_force(
    event: SecurityEvent,
    count: int,
    previous_event_ids: list[str],
) -> SecurityEvent:
    attributes = {
        **event.attributes,
        "count": count,
        "attackType": event.attributes.get("attackType") or "brute_force",
    }
    if previous_event_ids:
        attributes["aggregatedEventIds"] = [*previous_event_ids, event.id]
    return event.model_copy(
        update={"attributes": attributes, "severity": _failed_login_severity(event, count)}
    )


def _failed_login_severity(event: SecurityEvent, count: int) -> str:
    if event.severity in {"critical", "high"}:
        return event.severity
    return "high" if count >= 3 else event.severity


def _enrich_allowed_port_scan(event: SecurityEvent) -> SecurityEvent:
    if event.event_type != "network.event":
        return event

    if not _is_forwarded_scan_action(event):
        return event

    integration_id = event.attributes.get("integrationId") or event.entities.get("integrationId")
    source_ip = event.attributes.get("sourceIp") or event.entities.get("sourceIp")
    destination_ip = event.attributes.get("destinationIp") or event.entities.get("destinationIp")
    destination_port = _coerce_int(event.attributes.get("destinationPort"))
    if not integration_id or not source_ip or not destination_ip or destination_port is None:
        return event

    window_start = event.occurred_at - timedelta(seconds=ALLOWED_SCAN_WINDOW_SECONDS)
    if _has_recent_allowed_scan_event(
        integration_id=integration_id,
        source_ip=source_ip,
        destination_ip=destination_ip,
        window_start=window_start,
        occurred_at=event.occurred_at,
    ):
        return event

    ports: set[int] = {destination_port}
    related_event_ids: list[str] = [event.id] if event.id else []
    for payload in store.list_recent_events(
        event_type="network.event",
        limit=ALLOWED_SCAN_EVENT_LIMIT,
    ):
        previous = _load_event(payload)
        if previous.id == event.id:
            continue
        if previous.occurred_at < window_start or previous.occurred_at > event.occurred_at:
            continue
        if not _same_network_flow(event, previous):
            continue
        if not _is_forwarded_scan_action(previous):
            continue

        port = _coerce_int(previous.attributes.get("destinationPort"))
        if port is None:
            continue
        ports.add(port)
        if previous.id:
            related_event_ids.append(previous.id)

    if len(ports) < ALLOWED_SCAN_MIN_UNIQUE_PORTS:
        return event

    attributes = {
        **event.attributes,
        "integrationId": integration_id,
        "sourceIp": source_ip,
        "destinationIp": destination_ip,
        "attackType": "allowed_port_scan",
        "destinationPorts": sorted(ports),
        "uniqueDestinationPortCount": len(ports),
        "scanWindowSeconds": ALLOWED_SCAN_WINDOW_SECONDS,
        "relatedEventIds": related_event_ids,
    }
    return event.model_copy(
        update={
            "event_type": "network.scan",
            "severity": "high",
            "attributes": attributes,
        }
    )


def _is_forwarded_scan_action(event: SecurityEvent) -> bool:
    return str(event.attributes.get("action", "")).lower() in FORWARDED_SCAN_ACTIONS


def _same_network_flow(left: SecurityEvent, right: SecurityEvent) -> bool:
    for key in ("integrationId", "sourceIp", "destinationIp"):
        left_value = left.attributes.get(key) or left.entities.get(key)
        right_value = right.attributes.get(key) or right.entities.get(key)
        if left_value != right_value:
            return False
    return True


def _enrich_http_flood(event: SecurityEvent) -> SecurityEvent:
    if event.event_type != "network.event":
        return event
    if not _is_forwarded_scan_action(event):
        return event
    if not _is_http_flow(event):
        return event

    integration_id = event.attributes.get("integrationId") or event.entities.get("integrationId")
    source_ip = event.attributes.get("sourceIp") or event.entities.get("sourceIp")
    destination_ip = event.attributes.get("destinationIp") or event.entities.get("destinationIp")
    destination_port = _coerce_int(event.attributes.get("destinationPort"))
    if not integration_id or not source_ip or not destination_ip or destination_port is None:
        return event

    window_start = event.occurred_at - timedelta(seconds=HTTP_FLOOD_WINDOW_SECONDS)
    suppression_start = event.occurred_at - timedelta(seconds=HTTP_FLOOD_SUPPRESSION_SECONDS)
    if _has_recent_http_flood_event(
        integration_id=integration_id,
        source_ip=source_ip,
        destination_ip=destination_ip,
        destination_port=destination_port,
        window_start=suppression_start,
        occurred_at=event.occurred_at,
    ):
        return event

    count = 1
    related_event_ids: list[str] = [event.id] if event.id else []
    for payload in store.list_recent_events(
        event_type="network.event",
        limit=HTTP_FLOOD_EVENT_LIMIT,
    ):
        previous = _load_event(payload)
        if previous.id == event.id:
            continue
        if previous.occurred_at < window_start or previous.occurred_at > event.occurred_at:
            continue
        if not _same_http_flow(event, previous):
            continue
        if not _is_forwarded_scan_action(previous):
            continue

        count += max(1, _coerce_int(previous.attributes.get("count")) or 1)
        if previous.id:
            related_event_ids.append(previous.id)
        if count >= HTTP_FLOOD_MIN_EVENTS:
            break

    if count < HTTP_FLOOD_MIN_EVENTS:
        return event

    attributes = {
        **event.attributes,
        "integrationId": integration_id,
        "sourceIp": source_ip,
        "destinationIp": destination_ip,
        "destinationPort": destination_port,
        "attackType": "http_flood",
        "action": event.attributes.get("action") or "allow",
        "count": count,
        "floodWindowSeconds": HTTP_FLOOD_WINDOW_SECONDS,
        "relatedEventIds": related_event_ids,
        "ingestionMode": "fortigate_flow_inference",
    }
    return event.model_copy(
        update={
            "event_type": "waf.dos",
            "severity": "critical",
            "attributes": attributes,
        }
    )


def _is_http_flow(event: SecurityEvent) -> bool:
    service = str(event.attributes.get("service") or "").upper()
    if service in HTTP_FLOOD_SERVICES:
        return True
    destination_port = _coerce_int(event.attributes.get("destinationPort"))
    return destination_port in HTTP_FLOOD_PORTS


def _same_http_flow(left: SecurityEvent, right: SecurityEvent) -> bool:
    if not _same_network_flow(left, right):
        return False
    return _coerce_int(left.attributes.get("destinationPort")) == _coerce_int(
        right.attributes.get("destinationPort")
    )


def _has_recent_http_flood_event(
    *,
    integration_id: Any,
    source_ip: Any,
    destination_ip: Any,
    destination_port: int,
    window_start: datetime,
    occurred_at: datetime,
) -> bool:
    for payload in store.list_recent_events(event_type="waf.dos", limit=50):
        previous = _load_event(payload)
        if previous.occurred_at < window_start or previous.occurred_at > occurred_at:
            continue
        attributes = previous.attributes
        if attributes.get("attackType") != "http_flood":
            continue
        if attributes.get("ingestionMode") != "fortigate_flow_inference":
            continue
        if attributes.get("integrationId") != integration_id:
            continue
        if attributes.get("sourceIp") != source_ip:
            continue
        if attributes.get("destinationIp") != destination_ip:
            continue
        if _coerce_int(attributes.get("destinationPort")) != destination_port:
            continue
        return True
    return False


def _has_recent_allowed_scan_event(
    *,
    integration_id: Any,
    source_ip: Any,
    destination_ip: Any,
    window_start: datetime,
    occurred_at: datetime,
) -> bool:
    for payload in store.list_recent_events(event_type="network.scan", limit=50):
        previous = _load_event(payload)
        if previous.occurred_at < window_start or previous.occurred_at > occurred_at:
            continue
        attributes = previous.attributes
        if attributes.get("attackType") != "allowed_port_scan":
            continue
        if attributes.get("integrationId") != integration_id:
            continue
        if attributes.get("sourceIp") != source_ip:
            continue
        if attributes.get("destinationIp") != destination_ip:
            continue
        return True
    return False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/rules", response_model=list[DetectionRule])
def list_rules(enabled: bool | None = None) -> list[DetectionRule]:
    logger.info("siem_rules_list enabled=%s returned=%s", enabled, len(DETECTION_RULES))
    return DETECTION_RULES


@app.post("/events", response_model=SecurityEvent)
def create_event(event: SecurityEvent) -> SecurityEvent:
    stored_event, _incident = _ingest_event(event)
    return stored_event


@app.post("/events/ingest", response_model=EventIngestResult)
def ingest_event(event: SecurityEvent) -> EventIngestResult:
    stored_event, incident = _ingest_event(event)
    return EventIngestResult(event=stored_event, incident=incident)


def _ingest_event(event: SecurityEvent) -> tuple[SecurityEvent, Incident | None]:
    stored_event = event.model_copy(update={"id": event.id or _new_id("evt")})
    stored_event = _enrich_failed_login_burst(stored_event)
    stored_event = _enrich_allowed_port_scan(stored_event)
    stored_event = _enrich_http_flood(stored_event)
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
    return stored_event, incident


@app.post("/admin/reset")
def reset_store() -> dict[str, int]:
    deleted = store.reset()
    logger.info(
        "siem_store_reset events_deleted=%s incidents_deleted=%s",
        deleted.get("events"),
        deleted.get("incidents"),
    )
    return deleted


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
