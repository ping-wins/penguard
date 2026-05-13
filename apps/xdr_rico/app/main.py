import logging
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.store import XdrStore

SERVICE_NAME = "xdr_rico"
logger = logging.getLogger("uvicorn.error")
EndpointEventType = Literal[
    "heartbeat",
    "process.snapshot",
    "connection.snapshot",
    "auth.failed_login",
    "auth.privileged_logon",
    "login",
    "file.change",
    "suspicious.process",
    "health.signal",
]
EndpointHealth = Literal["unknown", "healthy", "warning", "critical", "offline"]


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class EnrollmentCreate(ApiModel):
    display_name: str | None = Field(default=None, alias="displayName", min_length=1)
    hostname_hint: str | None = Field(default=None, alias="hostnameHint", min_length=1)


class EnrollmentResponse(ApiModel):
    id: str
    display_name: str | None = Field(default=None, alias="displayName")
    hostname_hint: str | None = Field(default=None, alias="hostnameHint")
    created_at: datetime = Field(alias="createdAt")
    token: str


class EnrollmentRecord(ApiModel):
    id: str
    display_name: str | None = Field(default=None, alias="displayName")
    hostname_hint: str | None = Field(default=None, alias="hostnameHint")
    created_at: datetime = Field(alias="createdAt")
    token_hash: str = Field(alias="tokenHash")


class Endpoint(ApiModel):
    id: str
    hostname: str | None = None
    ip_addresses: list[str] = Field(default_factory=list, alias="ipAddresses")
    current_user: str | None = Field(default=None, alias="currentUser")
    last_seen_at: datetime | None = Field(default=None, alias="lastSeenAt")
    health: EndpointHealth = "unknown"
    attributes: dict[str, object] = Field(default_factory=dict)


class EndpointListResponse(ApiModel):
    items: list[Endpoint]


class EndpointEventCreate(ApiModel):
    endpoint_id: str = Field(alias="endpointId", min_length=1)
    event_type: EndpointEventType = Field(alias="eventType")
    occurred_at: datetime = Field(alias="occurredAt")
    hostname: str | None = None
    ip_addresses: list[str] | None = Field(default=None, alias="ipAddresses")
    current_user: str | None = Field(default=None, alias="currentUser")
    health: EndpointHealth | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


class EndpointTimelineItem(ApiModel):
    id: str
    endpoint_id: str = Field(alias="endpointId")
    event_type: EndpointEventType = Field(alias="eventType")
    occurred_at: datetime = Field(alias="occurredAt")
    title: str
    hostname: str | None = None
    ip_addresses: list[str] = Field(default_factory=list, alias="ipAddresses")
    current_user: str | None = Field(default=None, alias="currentUser")
    health: EndpointHealth | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


class EndpointTimelineResponse(ApiModel):
    endpoint_id: str = Field(alias="endpointId")
    items: list[EndpointTimelineItem]


class EndpointEventResponse(ApiModel):
    endpoint: Endpoint
    timeline_item: EndpointTimelineItem = Field(alias="timelineItem")


class SimulatorResponse(ApiModel):
    endpoint: Endpoint
    created_events: int = Field(alias="createdEvents")
    timeline: list[EndpointTimelineItem]


class CorrelationRequest(ApiModel):
    entities: dict[str, object] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=50)
    timeline_limit: int = Field(default=5, alias="timelineLimit", ge=0, le=50)


class MatchedField(ApiModel):
    field: str
    value: str
    matched_endpoint_field: str = Field(alias="matchedEndpointField")


class EndpointContextItem(ApiModel):
    endpoint: Endpoint
    score: int
    matched_fields: list[MatchedField] = Field(alias="matchedFields")
    timeline: list[EndpointTimelineItem] = Field(default_factory=list)


class EndpointContextResponse(ApiModel):
    incident_entities: dict[str, object] = Field(alias="incidentEntities")
    items: list[EndpointContextItem]
    total: int


app = FastAPI(title="xdr_rico", version="0.1.0")
app.state.xdr_store = XdrStore()


def reset_state() -> None:
    app.state.xdr_store.reset()


def now_utc() -> datetime:
    return datetime.now(UTC)


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_enrollment_token() -> str:
    return f"xdr_enroll_{uuid4().hex}"


def timeline_title(event_type: EndpointEventType) -> str:
    return event_type.replace(".", " ").replace("_", " ").title()


def get_store() -> XdrStore:
    return app.state.xdr_store


def get_endpoint_or_404(endpoint_id: str) -> Endpoint:
    payload = get_store().get_endpoint(endpoint_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint {endpoint_id} was not found.",
        )
    return _load_endpoint(payload)


def require_valid_enrollment_token(authorization: str | None) -> None:
    token = bearer_token(authorization)
    hashed_token = token_hash(token)
    if not get_store().has_enrollment_token_hash(hashed_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid endpoint enrollment token required.",
        )


def bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Endpoint enrollment token required.",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Endpoint enrollment token must use Bearer authentication.",
        )
    return token


def ingest_endpoint_event(event: EndpointEventCreate) -> EndpointEventResponse:
    store = get_store()
    endpoint_payload = store.get_endpoint(event.endpoint_id)
    endpoint = _load_endpoint(endpoint_payload) if endpoint_payload is not None else Endpoint(
        id=event.endpoint_id
    )
    endpoint.hostname = event.hostname or endpoint.hostname
    if event.ip_addresses is not None:
        endpoint.ip_addresses = event.ip_addresses
    endpoint.current_user = event.current_user or endpoint.current_user
    endpoint.last_seen_at = event.occurred_at
    endpoint.health = event.health or endpoint.health
    endpoint.attributes = {**endpoint.attributes, **event.attributes}
    store.upsert_endpoint(
        _dump(endpoint),
        hostname=endpoint.hostname,
        current_user=endpoint.current_user,
        health=endpoint.health,
        last_seen_at=endpoint.last_seen_at,
    )

    timeline_item = EndpointTimelineItem(
        id=f"tl_{uuid4().hex}",
        endpointId=endpoint.id,
        eventType=event.event_type,
        occurredAt=event.occurred_at,
        title=timeline_title(event.event_type),
        hostname=event.hostname,
        ipAddresses=event.ip_addresses or [],
        currentUser=event.current_user,
        health=event.health,
        attributes=event.attributes,
    )
    store.add_timeline_item(
        _dump(timeline_item),
        endpoint_id=endpoint.id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
    )
    logger.info(
        "xdr_endpoint_event_ingested endpoint_id=%s event_type=%s health=%s "
        "total_endpoints=%s endpoint_timeline_items=%s",
        endpoint.id,
        event.event_type,
        endpoint.health,
        store.count_endpoints(),
        store.count_timeline_items(endpoint.id),
    )
    return EndpointEventResponse(endpoint=endpoint, timelineItem=timeline_item)


def correlate_endpoint_context(payload: CorrelationRequest) -> EndpointContextResponse:
    store = get_store()
    endpoints = [_load_endpoint(endpoint_payload) for endpoint_payload in store.list_endpoints()]
    matches = [
        item
        for endpoint in endpoints
        if (item := _endpoint_context_item(endpoint, payload)) is not None
    ]
    matches.sort(
        key=lambda item: (
            item.score,
            item.endpoint.last_seen_at or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    limited_matches = matches[: payload.limit]
    logger.info(
        "xdr_endpoint_context_correlated entity_fields=%s matched=%s total_endpoints=%s",
        ",".join(sorted(payload.entities.keys())),
        len(limited_matches),
        store.count_endpoints(),
    )
    return EndpointContextResponse(
        incidentEntities=payload.entities,
        items=limited_matches,
        total=len(limited_matches),
    )


def _endpoint_context_item(
    endpoint: Endpoint,
    payload: CorrelationRequest,
) -> EndpointContextItem | None:
    matched_fields: list[MatchedField] = []
    score = 0

    for field, value in _entity_strings(payload.entities):
        normalized_field = field.lower()
        if (
            normalized_field in {"endpointid", "endpoint_id", "endpoint.id"}
            and value == endpoint.id
        ):
            matched_fields.append(
                MatchedField(field=field, value=value, matchedEndpointField="id")
            )
            score += 100
            continue

        if "ip" in normalized_field and value in endpoint.ip_addresses:
            matched_fields.append(
                MatchedField(field=field, value=value, matchedEndpointField="ipAddresses")
            )
            score += 50
            continue

        if normalized_field in {"hostname", "host", "endpointhostname"} and _same_text(
            value,
            endpoint.hostname,
        ):
            matched_fields.append(
                MatchedField(field=field, value=value, matchedEndpointField="hostname")
            )
            score += 30
            continue

        if normalized_field in {"username", "user", "currentuser", "current_user"} and _same_user(
            value,
            endpoint.current_user,
        ):
            matched_fields.append(
                MatchedField(field=field, value=value, matchedEndpointField="currentUser")
            )
            score += 20

    if not matched_fields:
        return None

    timeline = [
        _load_timeline_item(item)
        for item in get_store().list_timeline(endpoint.id, limit=payload.timeline_limit)
    ]
    return EndpointContextItem(
        endpoint=endpoint,
        score=score,
        matchedFields=matched_fields,
        timeline=timeline,
    )


def _entity_strings(entities: dict[str, object]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for field, raw_value in entities.items():
        if isinstance(raw_value, str) and raw_value:
            values.append((field, raw_value))
        elif isinstance(raw_value, list):
            values.extend((field, value) for value in raw_value if isinstance(value, str) and value)
    return values


def _same_text(left: str, right: str | None) -> bool:
    return bool(right) and left.casefold() == right.casefold()


def _same_user(left: str, right: str | None) -> bool:
    if not right:
        return False
    left_folded = left.casefold()
    right_folded = right.casefold()
    if left_folded == right_folded:
        return True
    return _principal_name(left_folded) == _principal_name(right_folded)


def _principal_name(value: str) -> str:
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    if "@" in value:
        value = value.split("@", 1)[0]
    return value


def _dump(model: ApiModel) -> dict[str, object]:
    return model.model_dump(by_alias=True, mode="json")


def _load_endpoint(payload: dict[str, object]) -> Endpoint:
    return Endpoint(**payload)


def _load_timeline_item(payload: dict[str, object]) -> EndpointTimelineItem:
    return EndpointTimelineItem(**payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post(
    "/enrollments",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment(payload: EnrollmentCreate) -> EnrollmentResponse:
    created_at = now_utc()
    enrollment_id = f"enr_{uuid4().hex}"
    token = create_enrollment_token()
    enrollment = EnrollmentRecord(
        id=enrollment_id,
        displayName=payload.display_name,
        hostnameHint=payload.hostname_hint,
        createdAt=created_at,
        tokenHash=token_hash(token),
    )
    get_store().add_enrollment(
        _dump(enrollment),
        token_hash=enrollment.token_hash,
        created_at=enrollment.created_at,
    )
    logger.info(
        "xdr_enrollment_created enrollment_id=%s display_name=%s hostname_hint=%s",
        enrollment_id,
        payload.display_name,
        payload.hostname_hint,
    )
    return EnrollmentResponse(
        id=enrollment_id,
        displayName=payload.display_name,
        hostnameHint=payload.hostname_hint,
        createdAt=created_at,
        token=token,
    )


@app.get("/endpoints", response_model=EndpointListResponse)
def list_endpoints() -> EndpointListResponse:
    items = [_load_endpoint(payload) for payload in get_store().list_endpoints()]
    logger.info("xdr_endpoints_list returned=%s", len(items))
    return EndpointListResponse(items=items)


@app.get("/endpoints/{endpoint_id}", response_model=Endpoint)
def get_endpoint(endpoint_id: str) -> Endpoint:
    return get_endpoint_or_404(endpoint_id)


@app.get("/endpoints/{endpoint_id}/timeline", response_model=EndpointTimelineResponse)
def get_endpoint_timeline(endpoint_id: str) -> EndpointTimelineResponse:
    get_endpoint_or_404(endpoint_id)
    items = [_load_timeline_item(payload) for payload in get_store().list_timeline(endpoint_id)]
    logger.info("xdr_endpoint_timeline endpoint_id=%s returned=%s", endpoint_id, len(items))
    return EndpointTimelineResponse(endpointId=endpoint_id, items=items)


@app.post(
    "/endpoint-events",
    response_model=EndpointEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_authorized_endpoint_event(
    payload: EndpointEventCreate,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> EndpointEventResponse:
    require_valid_enrollment_token(authorization)
    return ingest_endpoint_event(payload)


@app.post(
    "/simulator/events",
    response_model=SimulatorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_simulator_events() -> SimulatorResponse:
    store = get_store()
    endpoint_id = "demo-endpoint-01"
    store.delete_endpoint(endpoint_id)

    demo_events = [
        EndpointEventCreate(
            endpointId=endpoint_id,
            eventType="heartbeat",
            occurredAt=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            hostname="demo-endpoint-01",
            ipAddresses=["192.0.2.50"],
            currentUser="SOC-DEMO\\analyst",
            health="healthy",
            attributes={"os": "Linux", "source": "simulator"},
        ),
        EndpointEventCreate(
            endpointId=endpoint_id,
            eventType="process.snapshot",
            occurredAt=datetime(2026, 5, 8, 12, 1, tzinfo=UTC),
            hostname="demo-endpoint-01",
            ipAddresses=["192.0.2.50"],
            currentUser="SOC-DEMO\\analyst",
            attributes={
                "source": "simulator",
                "processes": [
                    {"pid": 1200, "name": "python", "username": "SOC-DEMO\\analyst"},
                    {"pid": 1250, "name": "curl", "username": "SOC-DEMO\\analyst"},
                ]
            },
        ),
        EndpointEventCreate(
            endpointId=endpoint_id,
            eventType="connection.snapshot",
            occurredAt=datetime(2026, 5, 8, 12, 2, tzinfo=UTC),
            hostname="demo-endpoint-01",
            ipAddresses=["192.0.2.50"],
            currentUser="SOC-DEMO\\analyst",
            attributes={
                "source": "simulator",
                "connections": [
                    {
                        "remoteIp": "198.51.100.20",
                        "remotePort": 443,
                        "state": "established",
                        "suspicious": True,
                    }
                ]
            },
        ),
        EndpointEventCreate(
            endpointId=endpoint_id,
            eventType="suspicious.process",
            occurredAt=datetime(2026, 5, 8, 12, 3, tzinfo=UTC),
            hostname="demo-endpoint-01",
            ipAddresses=["192.0.2.50"],
            currentUser="SOC-DEMO\\analyst",
            health="warning",
            attributes={
                "source": "simulator",
                "process": "curl",
                "remoteIp": "198.51.100.20",
                "reason": "unexpected outbound beacon pattern",
            },
        ),
    ]
    timeline_items = [ingest_endpoint_event(event).timeline_item for event in demo_events]
    endpoint = get_endpoint_or_404(endpoint_id)
    logger.info(
        "xdr_simulator_events_created endpoint_id=%s created_events=%s",
        endpoint_id,
        len(timeline_items),
    )
    return SimulatorResponse(
        endpoint=endpoint,
        createdEvents=len(timeline_items),
        timeline=sorted(timeline_items, key=lambda item: item.occurred_at, reverse=True),
    )


@app.post("/correlations/endpoint-context", response_model=EndpointContextResponse)
def create_endpoint_context_correlation(payload: CorrelationRequest) -> EndpointContextResponse:
    return correlate_endpoint_context(payload)
