import logging
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.store import SoarStore

SERVICE_NAME = "soar_skipper"
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="soar_skipper", version="0.1.0")

store = SoarStore()

NodeType = Literal[
    "trigger.incident_created",
    "condition.severity",
    "enrich.ip",
    "case.note",
    "audit.note",
    "approval.required",
    "notify.webhook",
    "fortigate.recommend_block",
    "fortiweb.recommend_block",
    "webhook.dry_run",
]
NodeCategory = Literal["trigger", "condition", "enrichment", "action", "control"]
ExecutionMode = Literal["dry_run", "live"]
NodeBoundary = Literal[
    "trigger_only",
    "decision_only",
    "enrichment_read_only",
    "case_note",
    "approval_gate",
    "notification_dry_run",
    "recommendation_only",
    "webhook_dry_run",
]
RunStatus = Literal["completed", "waiting_approval"]
StepStatus = Literal["completed", "waiting_approval"]

SENSITIVE_NODE_TYPES = {"fortigate.recommend_block", "fortiweb.recommend_block"}
APPROVAL_NODE_TYPES = {"approval.required"}


class PlaybookNode(BaseModel):
    id: str = Field(min_length=1)
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)


class PlaybookEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from", min_length=1)
    to_node: str = Field(alias="to", min_length=1)


class NodeTypeDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: NodeType
    label: str
    category: NodeCategory
    sensitive: bool = False
    dry_run_only: bool = Field(default=True, alias="dryRunOnly")
    execution_mode: ExecutionMode = Field(default="dry_run", alias="executionMode")
    live_available: bool = Field(default=False, alias="liveAvailable")
    boundary: NodeBoundary
    config_schema: dict[str, Any] = Field(default_factory=dict, alias="configSchema")


class NodeTypesResponse(BaseModel):
    items: list[NodeTypeDefinition]


class Playbook(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    enabled: bool = False
    nodes: list[PlaybookNode] = Field(min_length=1)
    edges: list[PlaybookEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "Playbook":
        node_ids = [node.id for node in self.nodes]
        unique_node_ids = set(node_ids)
        if len(unique_node_ids) != len(node_ids):
            raise ValueError("playbook node ids must be unique")

        missing_refs = [
            edge
            for edge in self.edges
            if edge.from_node not in unique_node_ids or edge.to_node not in unique_node_ids
        ]
        if missing_refs:
            raise ValueError("playbook edges must reference existing node ids")
        return self


class StepPreview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    node_id: str = Field(alias="nodeId")
    node_type: NodeType = Field(alias="nodeType")
    status: StepStatus
    sensitive: bool = False


class SimulationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dry_run: bool = Field(alias="dryRun")
    valid: bool
    steps: list[StepPreview]


class PlaybookStepRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    node_id: str = Field(alias="nodeId")
    node_type: NodeType = Field(alias="nodeType")
    status: StepStatus
    sensitive: bool = False
    created_at: datetime = Field(alias="createdAt")


class PlaybookRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    incident_id: str = Field(alias="incidentId")
    playbook_id: str = Field(alias="playbookId")
    dry_run: bool = Field(alias="dryRun")
    status: RunStatus
    steps: list[PlaybookStepRun]
    created_at: datetime = Field(alias="createdAt")


def _node_type_definitions() -> list[NodeTypeDefinition]:
    return [
        NodeTypeDefinition(
            id="trigger.incident_created",
            label="Incident Created",
            category="trigger",
            boundary="trigger_only",
            config_schema={"type": "object", "properties": {}},
        ),
        NodeTypeDefinition(
            id="condition.severity",
            label="Severity Condition",
            category="condition",
            boundary="decision_only",
            config_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "array",
                        "items": {"enum": ["low", "medium", "high", "critical"]},
                    }
                },
                "required": ["severity"],
            },
        ),
        NodeTypeDefinition(
            id="enrich.ip",
            label="Enrich IP",
            category="enrichment",
            boundary="enrichment_read_only",
            config_schema={
                "type": "object",
                "properties": {"field": {"type": "string"}},
                "required": ["field"],
            },
        ),
        NodeTypeDefinition(
            id="case.note",
            label="Create Case Note",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {"template": {"type": "string"}},
                "required": ["template"],
            },
        ),
        NodeTypeDefinition(
            id="audit.note",
            label="Write Audit Note",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        ),
        NodeTypeDefinition(
            id="approval.required",
            label="Require Approval",
            category="control",
            boundary="approval_gate",
            config_schema={
                "type": "object",
                "properties": {"role": {"type": "string", "default": "admin"}},
            },
        ),
        NodeTypeDefinition(
            id="notify.webhook",
            label="Notify Webhook",
            category="action",
            boundary="notification_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "mode": {"enum": ["dry_run"]},
                    "channel": {"type": "string"},
                },
            },
        ),
        NodeTypeDefinition(
            id="fortigate.recommend_block",
            label="Recommend FortiGate Block",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "mode": {"enum": ["dry_run"]},
                    "field": {"type": "string"},
                },
                "required": ["field"],
            },
        ),
        NodeTypeDefinition(
            id="fortiweb.recommend_block",
            label="Recommend FortiWeb Block",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "sourceIp": {"type": "string"},
                    "durationMinutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 60,
                    },
                },
                "required": ["sourceIp"],
            },
        ),
        NodeTypeDefinition(
            id="webhook.dry_run",
            label="Webhook Dry Run",
            category="action",
            boundary="webhook_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"enum": ["POST"]},
                },
            },
        ),
    ]


def _default_playbooks() -> list[Playbook]:
    return [
        Playbook(
            id="pb_port_scan_triage",
            name="Port Scan Triage",
            enabled=False,
            nodes=[
                PlaybookNode(id="trigger", type="trigger.incident_created"),
                PlaybookNode(
                    id="severity",
                    type="condition.severity",
                    config={"severity": ["high", "critical"]},
                ),
                PlaybookNode(
                    id="enrich_source_ip",
                    type="enrich.ip",
                    config={"field": "entities.sourceIp"},
                ),
                PlaybookNode(id="approval", type="approval.required", config={"role": "admin"}),
                PlaybookNode(
                    id="recommend_block",
                    type="fortigate.recommend_block",
                    config={"mode": "dry_run", "field": "entities.sourceIp"},
                ),
            ],
            edges=[
                PlaybookEdge(from_node="trigger", to_node="severity"),
                PlaybookEdge(from_node="severity", to_node="enrich_source_ip"),
                PlaybookEdge(from_node="enrich_source_ip", to_node="approval"),
                PlaybookEdge(from_node="approval", to_node="recommend_block"),
            ],
        ),
        Playbook(
            id="pb_suspicious_endpoint_triage",
            name="Suspicious Endpoint Triage",
            enabled=False,
            nodes=[
                PlaybookNode(id="trigger", type="trigger.incident_created"),
                PlaybookNode(
                    id="severity",
                    type="condition.severity",
                    config={"severity": ["medium", "high", "critical"]},
                ),
                PlaybookNode(
                    id="enrich_endpoint_ip",
                    type="enrich.ip",
                    config={"field": "entities.endpointIp"},
                ),
                PlaybookNode(
                    id="case_note",
                    type="case.note",
                    config={"template": "Review endpoint telemetry before response."},
                ),
                PlaybookNode(
                    id="notify",
                    type="notify.webhook",
                    config={"mode": "dry_run", "channel": "soc"},
                ),
            ],
            edges=[
                PlaybookEdge(from_node="trigger", to_node="severity"),
                PlaybookEdge(from_node="severity", to_node="enrich_endpoint_ip"),
                PlaybookEdge(from_node="enrich_endpoint_ip", to_node="case_note"),
                PlaybookEdge(from_node="case_note", to_node="notify"),
            ],
        ),
    ]


def _seed_default_playbooks() -> None:
    """Insert the default disabled playbooks the first time the service comes
    up against an empty store. Subsequent restarts are idempotent — the
    operator's custom playbooks stay intact.
    """
    for playbook in _default_playbooks():
        if store.get_playbook(playbook.id) is None:
            store.save_playbook(playbook.id, _playbook_to_payload(playbook))


def _playbook_to_payload(playbook: Playbook) -> dict[str, Any]:
    return playbook.model_dump(mode="json", by_alias=True)


def _payload_to_playbook(payload: dict[str, Any]) -> Playbook:
    return Playbook.model_validate(payload)


def _run_to_payload(run: PlaybookRun) -> dict[str, Any]:
    return run.model_dump(mode="json", by_alias=True)


def _payload_to_run(payload: dict[str, Any]) -> PlaybookRun:
    return PlaybookRun.model_validate(payload)


_seed_default_playbooks()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/node-types", response_model=NodeTypesResponse)
def list_node_types() -> NodeTypesResponse:
    items = _node_type_definitions()
    logger.info("soar_node_types_list returned=%s", len(items))
    return NodeTypesResponse(items=items)


@app.get("/playbooks", response_model=list[Playbook])
def list_playbooks() -> list[Playbook]:
    results = [_payload_to_playbook(payload) for payload in store.list_playbooks()]
    logger.info("soar_playbooks_list returned=%s", len(results))
    return results


@app.post("/playbooks", response_model=Playbook, status_code=status.HTTP_201_CREATED)
def create_playbook(playbook: Playbook) -> Playbook:
    if store.get_playbook(playbook.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"playbook {playbook.id} already exists",
        )
    store.save_playbook(playbook.id, _playbook_to_payload(playbook))
    logger.info(
        "soar_playbook_created playbook_id=%s enabled=%s nodes=%s",
        playbook.id,
        playbook.enabled,
        len(playbook.nodes),
    )
    return playbook


@app.get("/playbooks/{playbook_id}", response_model=Playbook)
def get_playbook(playbook_id: str) -> Playbook:
    return _get_playbook_or_404(playbook_id)


@app.put("/playbooks/{playbook_id}", response_model=Playbook)
def update_playbook(playbook_id: str, playbook: Playbook) -> Playbook:
    if playbook.id != playbook_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="playbook id must match path",
        )
    _get_playbook_or_404(playbook_id)
    store.update_playbook(playbook_id, _playbook_to_payload(playbook))
    logger.info(
        "soar_playbook_updated playbook_id=%s enabled=%s nodes=%s",
        playbook_id,
        playbook.enabled,
        len(playbook.nodes),
    )
    return playbook


@app.post("/playbooks/{playbook_id}/simulate", response_model=SimulationResponse)
def simulate_playbook(playbook_id: str) -> SimulationResponse:
    playbook = _get_playbook_or_404(playbook_id)
    steps = _build_step_previews(playbook)
    logger.info(
        "soar_playbook_simulated playbook_id=%s steps=%s",
        playbook_id,
        len(steps),
    )
    return SimulationResponse(dry_run=True, valid=True, steps=steps)


@app.post(
    "/incidents/{incident_id}/playbooks/{playbook_id}/run",
    response_model=PlaybookRun,
    status_code=status.HTTP_201_CREATED,
)
def run_playbook(incident_id: str, playbook_id: str) -> PlaybookRun:
    playbook = _get_playbook_or_404(playbook_id)
    now = _utc_now()
    steps = [
        PlaybookStepRun(
            id=f"step_{index + 1}",
            node_id=preview.node_id,
            node_type=preview.node_type,
            status=preview.status,
            sensitive=preview.sensitive,
            created_at=now,
        )
        for index, preview in enumerate(_build_step_previews(playbook))
    ]
    has_waiting_step = any(step.status == "waiting_approval" for step in steps)
    run_status: RunStatus = "waiting_approval" if has_waiting_step else "completed"
    run = PlaybookRun(
        id=f"run_{uuid4().hex}",
        incident_id=incident_id,
        playbook_id=playbook_id,
        dry_run=True,
        status=run_status,
        steps=steps,
        created_at=now,
    )
    store.save_run(
        _run_to_payload(run),
        incident_id=run.incident_id,
        playbook_id=run.playbook_id,
        status=run.status,
        created_at=run.created_at,
    )
    logger.info(
        "soar_playbook_run_created run_id=%s incident_id=%s playbook_id=%s status=%s "
        "dry_run=%s steps=%s",
        run.id,
        incident_id,
        playbook_id,
        run.status,
        run.dry_run,
        len(run.steps),
    )
    return run


@app.get("/playbook-runs/{run_id}", response_model=PlaybookRun)
def get_playbook_run(run_id: str) -> PlaybookRun:
    payload = store.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook run not found")
    return _payload_to_run(payload)


@app.post("/playbook-runs/{run_id}/approve", response_model=PlaybookRun)
def approve_playbook_run(run_id: str) -> PlaybookRun:
    payload = store.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook run not found")
    run = _payload_to_run(payload)
    approved = run.model_copy(
        update={
            "status": "completed",
            "steps": [
                step.model_copy(update={"status": "completed"})
                if step.status == "waiting_approval"
                else step
                for step in run.steps
            ],
        }
    )
    store.update_run(_run_to_payload(approved), status=approved.status)
    logger.info("soar_playbook_run_approved run_id=%s", run_id)
    return approved


@app.get("/playbook-runs", response_model=list[PlaybookRun])
def list_playbook_runs(status: RunStatus | None = None) -> list[PlaybookRun]:
    payloads = store.list_runs(status=status)
    runs = [_payload_to_run(payload) for payload in payloads]
    logger.info(
        "soar_playbook_runs_list status=%s returned=%s",
        status,
        len(runs),
    )
    return runs


def _get_playbook_or_404(playbook_id: str) -> Playbook:
    payload = store.get_playbook(playbook_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook not found")
    return _payload_to_playbook(payload)


def _build_step_previews(playbook: Playbook) -> list[StepPreview]:
    return [
        StepPreview(
            node_id=node.id,
            node_type=node.type,
            status=_status_for_node(node),
            sensitive=node.type in SENSITIVE_NODE_TYPES,
        )
        for node in _ordered_nodes(playbook)
    ]


def _status_for_node(node: PlaybookNode) -> StepStatus:
    if node.type in SENSITIVE_NODE_TYPES or node.type in APPROVAL_NODE_TYPES:
        return "waiting_approval"
    return "completed"


def _ordered_nodes(playbook: Playbook) -> list[PlaybookNode]:
    nodes_by_id = {node.id: node for node in playbook.nodes}
    input_order = {node.id: index for index, node in enumerate(playbook.nodes)}
    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree = {node.id: 0 for node in playbook.nodes}

    for edge in playbook.edges:
        outgoing[edge.from_node].append(edge.to_node)
        indegree[edge.to_node] += 1

    starting_node_ids = (node_id for node_id, degree in indegree.items() if degree == 0)
    queue = deque(sorted(starting_node_ids, key=input_order.get))
    ordered_ids: list[str] = []

    while queue:
        node_id = queue.popleft()
        ordered_ids.append(node_id)
        for next_node_id in sorted(outgoing[node_id], key=input_order.get):
            indegree[next_node_id] -= 1
            if indegree[next_node_id] == 0:
                queue.append(next_node_id)

    if len(ordered_ids) != len(playbook.nodes):
        return playbook.nodes

    return [nodes_by_id[node_id] for node_id in ordered_ids]


def _utc_now() -> datetime:
    return datetime.now(UTC)
