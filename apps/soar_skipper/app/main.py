from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

SERVICE_NAME = "soar_skipper"

app = FastAPI(title="soar_skipper", version="0.1.0")

NodeType = Literal[
    "trigger.incident_created",
    "condition.severity",
    "enrich.ip",
    "case.note",
    "approval.required",
    "notify.webhook",
    "fortigate.recommend_block",
    "webhook.dry_run",
]
RunStatus = Literal["completed", "waiting_approval"]
StepStatus = Literal["completed", "waiting_approval"]

SENSITIVE_NODE_TYPES = {"fortigate.recommend_block"}
APPROVAL_NODE_TYPES = {"approval.required"}


class PlaybookNode(BaseModel):
    id: str = Field(min_length=1)
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)


class PlaybookEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from", min_length=1)
    to_node: str = Field(alias="to", min_length=1)


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


def _default_playbooks() -> dict[str, Playbook]:
    defaults = [
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
    return {playbook.id: playbook for playbook in defaults}


playbooks: dict[str, Playbook] = _default_playbooks()
playbook_runs: dict[str, PlaybookRun] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/playbooks", response_model=list[Playbook])
def list_playbooks() -> list[Playbook]:
    return list(playbooks.values())


@app.post("/playbooks", response_model=Playbook, status_code=status.HTTP_201_CREATED)
def create_playbook(playbook: Playbook) -> Playbook:
    if playbook.id in playbooks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"playbook {playbook.id} already exists",
        )
    playbooks[playbook.id] = playbook
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
    playbooks[playbook_id] = playbook
    return playbook


@app.post("/playbooks/{playbook_id}/simulate", response_model=SimulationResponse)
def simulate_playbook(playbook_id: str) -> SimulationResponse:
    playbook = _get_playbook_or_404(playbook_id)
    return SimulationResponse(dry_run=True, valid=True, steps=_build_step_previews(playbook))


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
    playbook_runs[run.id] = run
    return run


@app.get("/playbook-runs/{run_id}", response_model=PlaybookRun)
def get_playbook_run(run_id: str) -> PlaybookRun:
    run = playbook_runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook run not found")
    return run


@app.get("/playbook-runs", response_model=list[PlaybookRun])
def list_playbook_runs(status: RunStatus | None = None) -> list[PlaybookRun]:
    runs = sorted(
        playbook_runs.values(),
        key=lambda run: run.created_at,
        reverse=True,
    )
    if status is not None:
        return [run for run in runs if run.status == status]
    return runs


def _get_playbook_or_404(playbook_id: str) -> Playbook:
    playbook = playbooks.get(playbook_id)
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook not found")
    return playbook


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
