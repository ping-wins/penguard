import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, status

from app.graph_validation import validate_playbook_for_save
from app.models import (
    NodeTypesResponse,
    Playbook,
    PlaybookEdge,
    PlaybookNode,
    PlaybookRun,
    RunStatus,
    SimulationResponse,
)
from app.node_catalog import node_type_definitions
from app.runtime import build_playbook_run, build_step_previews
from app.store import SoarStore

SERVICE_NAME = "soar_skipper"
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="soar_skipper", version="0.1.0")

store = SoarStore()


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
                    type="fortigate.temporary_block",
                    config={
                        "scope": "source_only",
                        "durationMinutes": 30,
                        "sourceField": "entities.sourceIp",
                    },
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
    """Insert default disabled playbooks only when the store is empty."""
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
    items = node_type_definitions()
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
    validation_errors = validate_playbook_for_save(playbook)
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": validation_errors},
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
    validation_errors = validate_playbook_for_save(playbook)
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": validation_errors},
        )
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
    steps = build_step_previews(playbook)
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
    run = build_playbook_run(playbook, incident_id=incident_id, now=_utc_now())
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
            "node_runs": [
                node.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": _utc_now(),
                    }
                )
                if node.status == "waiting_approval"
                else node
                for node in run.node_runs
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


def _utc_now() -> datetime:
    return datetime.now(UTC)
