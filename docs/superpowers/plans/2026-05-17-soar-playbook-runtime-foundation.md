# SOAR Playbook Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `soar_skipper` into a graph-runtime foundation that preserves existing SOAR APIs while adding versioned playbook payloads, graph validation, node-level run state and edge traversal records.

**Architecture:** Split the current monolithic `apps/soar_skipper/app/main.py` into focused modules: models, node catalog, graph validation and runtime. Keep the FastAPI surface compatible, but make run payloads richer by adding `nodeRuns` and `edgeTraversals` alongside the existing `steps` field.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy-backed `SoarStore`, Pytest, Ruff.

---

## File Structure

- Create `apps/soar_skipper/app/models.py`: Pydantic types and shared literals.
- Create `apps/soar_skipper/app/node_catalog.py`: node catalog definitions and safety sets.
- Create `apps/soar_skipper/app/graph_validation.py`: graph validation helpers that can be reused by save and runtime.
- Create `apps/soar_skipper/app/runtime.py`: deterministic ordering, simulation previews and run construction.
- Modify `apps/soar_skipper/app/main.py`: route wiring only.
- Modify `apps/soar_skipper/tests/test_playbooks.py`: keep existing endpoint expectations and add assertions for enriched run payload.
- Create `apps/soar_skipper/tests/test_graph_runtime.py`: direct unit coverage for graph validation and runtime helpers.

## Task 1: Add Graph Runtime Tests First

**Files:**
- Create: `apps/soar_skipper/tests/test_graph_runtime.py`
- Modify: `apps/soar_skipper/tests/test_playbooks.py`

- [ ] **Step 1: Write direct runtime tests**

Create `apps/soar_skipper/tests/test_graph_runtime.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Playbook, PlaybookEdge, PlaybookNode
from app.runtime import build_playbook_run, build_step_previews, ordered_nodes


def test_ordered_nodes_accepts_branched_edges_without_losing_nodes():
    playbook = Playbook(
        id="pb_branch",
        name="Branching playbook",
        nodes=[
            PlaybookNode(id="trigger", type="trigger.incident_created"),
            PlaybookNode(id="severity", type="condition.severity"),
            PlaybookNode(id="note_high", type="case.note", config={"template": "High"}),
            PlaybookNode(id="note_low", type="case.note", config={"template": "Low"}),
        ],
        edges=[
            PlaybookEdge(from_node="trigger", to_node="severity"),
            PlaybookEdge(from_node="severity", to_node="note_high", condition="true"),
            PlaybookEdge(from_node="severity", to_node="note_low", condition="false"),
        ],
    )

    assert [node.id for node in ordered_nodes(playbook)] == [
        "trigger",
        "severity",
        "note_high",
        "note_low",
    ]


def test_playbook_rejects_duplicate_node_ids():
    with pytest.raises(ValidationError, match="playbook node ids must be unique"):
        Playbook(
            id="pb_duplicate",
            name="Duplicate nodes",
            nodes=[
                PlaybookNode(id="trigger", type="trigger.incident_created"),
                PlaybookNode(id="trigger", type="case.note"),
            ],
        )


def test_playbook_rejects_edges_to_missing_nodes():
    with pytest.raises(ValidationError, match="playbook edges must reference existing node ids"):
        Playbook(
            id="pb_missing_edge",
            name="Missing edge target",
            nodes=[PlaybookNode(id="trigger", type="trigger.incident_created")],
            edges=[PlaybookEdge(from_node="trigger", to_node="missing")],
        )


def test_build_playbook_run_records_node_runs_and_edge_traversals():
    now = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    playbook = Playbook(
        id="pb_runtime",
        name="Runtime",
        nodes=[
            PlaybookNode(id="trigger", type="trigger.incident_created"),
            PlaybookNode(id="approval", type="approval.required"),
            PlaybookNode(id="block", type="fortigate.temporary_block"),
        ],
        edges=[
            PlaybookEdge(from_node="trigger", to_node="approval"),
            PlaybookEdge(from_node="approval", to_node="block", condition="approved"),
        ],
    )

    run = build_playbook_run(playbook, incident_id="inc_123", now=now)

    assert run.status == "waiting_approval"
    assert [step.node_id for step in run.steps] == ["trigger", "approval", "block"]
    assert [node.node_id for node in run.node_runs] == ["trigger", "approval", "block"]
    assert [edge.condition for edge in run.edge_traversals] == ["success", "approved"]
    assert run.node_runs[1].status == "waiting_approval"


def test_build_step_previews_stays_backwards_compatible():
    playbook = Playbook(
        id="pb_preview",
        name="Preview",
        nodes=[
            PlaybookNode(id="trigger", type="trigger.incident_created"),
            PlaybookNode(id="note", type="case.note"),
        ],
        edges=[PlaybookEdge(from_node="trigger", to_node="note")],
    )

    assert [step.model_dump(by_alias=True) for step in build_step_previews(playbook)] == [
        {
            "nodeId": "trigger",
            "nodeType": "trigger.incident_created",
            "status": "completed",
            "sensitive": False,
        },
        {
            "nodeId": "note",
            "nodeType": "case.note",
            "status": "completed",
            "sensitive": False,
        },
    ]
```

- [ ] **Step 2: Add endpoint-level enriched run assertions**

In `apps/soar_skipper/tests/test_playbooks.py`, extend `test_run_playbook_requires_approval_for_sensitive_nodes` after `body = response.json()`:

```python
    assert [node["nodeId"] for node in body["nodeRuns"]] == [
        "trigger",
        "severity",
        "enrich_source_ip",
        "approval",
        "recommend_block",
    ]
    assert body["nodeRuns"][-1]["status"] == "waiting_approval"
    assert body["edgeTraversals"][-1]["condition"] == "success"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_graph_runtime.py tests/test_playbooks.py
```

Expected: `tests/test_graph_runtime.py` fails with `ModuleNotFoundError` for `app.models` or `app.runtime`.

## Task 2: Extract Shared Models

**Files:**
- Create: `apps/soar_skipper/app/models.py`
- Modify: `apps/soar_skipper/app/main.py`

- [ ] **Step 1: Create the models module**

Create `apps/soar_skipper/app/models.py`:

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "fortigate.temporary_block",
    "webhook.dry_run",
]
NodeCategory = Literal["trigger", "condition", "enrichment", "action", "control"]
ExecutionMode = Literal["dry_run", "live", "approval_required"]
NodeBoundary = Literal[
    "trigger_only",
    "decision_only",
    "enrichment_read_only",
    "case_note",
    "approval_gate",
    "notification_dry_run",
    "recommendation_only",
    "fortigate_policy_orchestration",
    "webhook_dry_run",
]
RunStatus = Literal[
    "pending",
    "running",
    "completed",
    "waiting_approval",
    "failed",
    "timed_out",
    "cancelled",
]
StepStatus = Literal[
    "pending",
    "running",
    "completed",
    "skipped",
    "failed",
    "waiting_approval",
    "timed_out",
    "cancelled",
]
EdgeCondition = Literal[
    "success",
    "failure",
    "true",
    "false",
    "approved",
    "rejected",
    "loop_next",
    "loop_done",
]


class PlaybookNode(BaseModel):
    id: str = Field(min_length=1)
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)


class PlaybookEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from", min_length=1)
    to_node: str = Field(alias="to", min_length=1)
    condition: EdgeCondition = "success"


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
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, alias="schemaVersion", ge=1)
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    enabled: bool = False
    nodes: list[PlaybookNode] = Field(min_length=1)
    edges: list[PlaybookEdge] = Field(default_factory=list)
    runtime_policy: dict[str, Any] = Field(default_factory=dict, alias="runtimePolicy")

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


class PlaybookNodeRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    node_id: str = Field(alias="nodeId")
    node_type: NodeType = Field(alias="nodeType")
    status: StepStatus
    sensitive: bool = False
    attempt: int = 1
    iteration: int = 0
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    error: str | None = None


class EdgeTraversal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    condition: EdgeCondition = "success"
    created_at: datetime = Field(alias="createdAt")


class PlaybookRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    incident_id: str = Field(alias="incidentId")
    playbook_id: str = Field(alias="playbookId")
    dry_run: bool = Field(alias="dryRun")
    status: RunStatus
    steps: list[PlaybookStepRun]
    node_runs: list[PlaybookNodeRun] = Field(default_factory=list, alias="nodeRuns")
    edge_traversals: list[EdgeTraversal] = Field(default_factory=list, alias="edgeTraversals")
    created_at: datetime = Field(alias="createdAt")
```

- [ ] **Step 2: Replace local model definitions in `main.py`**

Modify the imports at the top of `apps/soar_skipper/app/main.py` to import the new models:

```python
from app.models import (
    NodeTypesResponse,
    Playbook,
    PlaybookEdge,
    PlaybookRun,
    PlaybookStepRun,
    RunStatus,
    SimulationResponse,
    StepPreview,
    StepStatus,
)
```

Delete the duplicated literal and class definitions from `main.py`.

- [ ] **Step 3: Run tests**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_playbooks.py
```

Expected: existing playbook tests still pass or fail only because helper modules are not extracted yet.

## Task 3: Extract Node Catalog And Runtime Helpers

**Files:**
- Create: `apps/soar_skipper/app/node_catalog.py`
- Create: `apps/soar_skipper/app/runtime.py`
- Modify: `apps/soar_skipper/app/main.py`

- [ ] **Step 1: Create node catalog module**

Move `_node_type_definitions`, `SENSITIVE_NODE_TYPES` and `APPROVAL_NODE_TYPES` from `main.py` into `apps/soar_skipper/app/node_catalog.py`.

Keep this public surface:

```python
from app.models import NodeTypeDefinition

SENSITIVE_NODE_TYPES = {
    "fortigate.recommend_block",
    "fortigate.temporary_block",
    "fortiweb.recommend_block",
}
APPROVAL_NODE_TYPES = {"approval.required"}


def node_type_definitions() -> list[NodeTypeDefinition]:
    return [
        # Move the existing NodeTypeDefinition entries here unchanged.
    ]
```

- [ ] **Step 2: Create runtime module**

Create `apps/soar_skipper/app/runtime.py`:

```python
from datetime import datetime
from uuid import uuid4

from app.models import (
    EdgeTraversal,
    Playbook,
    PlaybookNode,
    PlaybookNodeRun,
    PlaybookRun,
    PlaybookStepRun,
    RunStatus,
    StepPreview,
    StepStatus,
)
from app.node_catalog import APPROVAL_NODE_TYPES, SENSITIVE_NODE_TYPES


def build_step_previews(playbook: Playbook) -> list[StepPreview]:
    return [
        StepPreview(
            node_id=node.id,
            node_type=node.type,
            status=status_for_node(node),
            sensitive=node.type in SENSITIVE_NODE_TYPES,
        )
        for node in ordered_nodes(playbook)
    ]


def build_playbook_run(playbook: Playbook, *, incident_id: str, now: datetime) -> PlaybookRun:
    previews = build_step_previews(playbook)
    steps = [
        PlaybookStepRun(
            id=f"step_{index + 1}",
            node_id=preview.node_id,
            node_type=preview.node_type,
            status=preview.status,
            sensitive=preview.sensitive,
            created_at=now,
        )
        for index, preview in enumerate(previews)
    ]
    node_runs = [
        PlaybookNodeRun(
            id=f"node_run_{index + 1}",
            node_id=preview.node_id,
            node_type=preview.node_type,
            status=preview.status,
            sensitive=preview.sensitive,
            started_at=now,
            completed_at=None if preview.status == "waiting_approval" else now,
        )
        for index, preview in enumerate(previews)
    ]
    edge_traversals = [
        EdgeTraversal(
            id=f"edge_traversal_{index + 1}",
            from_node=edge.from_node,
            to_node=edge.to_node,
            condition=edge.condition,
            created_at=now,
        )
        for index, edge in enumerate(playbook.edges)
    ]
    has_waiting_step = any(step.status == "waiting_approval" for step in steps)
    run_status: RunStatus = "waiting_approval" if has_waiting_step else "completed"
    return PlaybookRun(
        id=f"run_{uuid4().hex}",
        incident_id=incident_id,
        playbook_id=playbook.id,
        dry_run=True,
        status=run_status,
        steps=steps,
        node_runs=node_runs,
        edge_traversals=edge_traversals,
        created_at=now,
    )


def status_for_node(node: PlaybookNode) -> StepStatus:
    if node.type in SENSITIVE_NODE_TYPES or node.type in APPROVAL_NODE_TYPES:
        return "waiting_approval"
    return "completed"


def ordered_nodes(playbook: Playbook) -> list[PlaybookNode]:
    nodes_by_id = {node.id: node for node in playbook.nodes}
    input_order = {node.id: index for index, node in enumerate(playbook.nodes)}
    outgoing: dict[str, list[str]] = {node.id: [] for node in playbook.nodes}
    indegree = {node.id: 0 for node in playbook.nodes}

    for edge in playbook.edges:
        outgoing.setdefault(edge.from_node, []).append(edge.to_node)
        indegree[edge.to_node] += 1

    queue = sorted(
        [node_id for node_id, degree in indegree.items() if degree == 0],
        key=input_order.get,
    )
    ordered_ids: list[str] = []

    while queue:
        node_id = queue.pop(0)
        ordered_ids.append(node_id)
        for next_node_id in sorted(outgoing.get(node_id, []), key=input_order.get):
            indegree[next_node_id] -= 1
            if indegree[next_node_id] == 0:
                queue.append(next_node_id)

    if len(ordered_ids) != len(playbook.nodes):
        return playbook.nodes
    return [nodes_by_id[node_id] for node_id in ordered_ids]
```

- [ ] **Step 3: Wire `main.py` to the extracted helpers**

In `apps/soar_skipper/app/main.py`:

```python
from app.node_catalog import node_type_definitions
from app.runtime import build_playbook_run, build_step_previews
```

Then update route helpers:

```python
@app.get("/node-types", response_model=NodeTypesResponse)
def list_node_types() -> NodeTypesResponse:
    items = node_type_definitions()
    logger.info("soar_node_types_list returned=%s", len(items))
    return NodeTypesResponse(items=items)


@app.post("/playbooks/{playbook_id}/simulate", response_model=SimulationResponse)
def simulate_playbook(playbook_id: str) -> SimulationResponse:
    playbook = _get_playbook_or_404(playbook_id)
    steps = build_step_previews(playbook)
    logger.info("soar_playbook_simulated playbook_id=%s steps=%s", playbook_id, len(steps))
    return SimulationResponse(dry_run=True, valid=True, steps=steps)


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
    return run
```

Preserve the existing route decorator and logging around `run_playbook`.

- [ ] **Step 4: Run tests**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_graph_runtime.py tests/test_playbooks.py
```

Expected: all selected tests pass.

## Task 4: Add Validation Module Boundary

**Files:**
- Create: `apps/soar_skipper/app/graph_validation.py`
- Modify: `apps/soar_skipper/app/main.py`
- Modify: `apps/soar_skipper/tests/test_graph_runtime.py`

- [ ] **Step 1: Add validation tests**

Append to `apps/soar_skipper/tests/test_graph_runtime.py`:

```python
from app.graph_validation import validate_playbook_for_save


def test_validate_playbook_for_save_requires_trigger():
    playbook = Playbook(
        id="pb_no_trigger",
        name="No trigger",
        nodes=[PlaybookNode(id="note", type="case.note")],
    )

    errors = validate_playbook_for_save(playbook)

    assert errors == ["playbook must include at least one trigger node"]


def test_validate_playbook_for_save_accepts_default_playbook_shape():
    playbook = Playbook(
        id="pb_ok",
        name="OK",
        nodes=[
            PlaybookNode(id="trigger", type="trigger.incident_created"),
            PlaybookNode(id="note", type="case.note"),
        ],
        edges=[PlaybookEdge(from_node="trigger", to_node="note")],
    )

    assert validate_playbook_for_save(playbook) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_graph_runtime.py::test_validate_playbook_for_save_requires_trigger
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph_validation'`.

- [ ] **Step 3: Implement validation helper**

Create `apps/soar_skipper/app/graph_validation.py`:

```python
from app.models import Playbook


def validate_playbook_for_save(playbook: Playbook) -> list[str]:
    errors: list[str] = []
    if not any(node.type.startswith("trigger.") for node in playbook.nodes):
        errors.append("playbook must include at least one trigger node")
    return errors
```

- [ ] **Step 4: Use validation on create and update**

In `apps/soar_skipper/app/main.py`, import:

```python
from app.graph_validation import validate_playbook_for_save
```

In `create_playbook` and `update_playbook`, before saving:

```python
    validation_errors = validate_playbook_for_save(playbook)
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": validation_errors},
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_graph_runtime.py tests/test_playbooks.py
```

Expected: all selected tests pass. If an existing test creates a playbook without a trigger, update that test fixture to include `PlaybookNode(id="trigger", type="trigger.incident_created")`.

## Task 5: Final Verification And Commit

**Files:**
- All files changed by Tasks 1-4.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd apps/soar_skipper && uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 2: Run SOAR tests**

Run:

```bash
cd apps/soar_skipper && uv run pytest -q
```

Expected: all SOAR tests pass.

- [ ] **Step 3: Run compose config**

Run:

```bash
docker compose config --quiet
```

Expected: no output and exit code 0.

- [ ] **Step 4: Review diff**

Run:

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors; changed files limited to `apps/soar_skipper` plus this plan/spec if uncommitted.

- [ ] **Step 5: Commit phase 1**

Run:

```bash
git add apps/soar_skipper docs/superpowers/plans/2026-05-17-soar-playbook-runtime-foundation.md
git commit -m "feat(soar): add playbook graph runtime foundation"
```

Expected: one commit containing the runtime foundation and plan document if not already committed.

---

## Self-Review

- Spec coverage: This plan covers Phase 1 from the design spec: model split, node catalog split, graph validation, versioned payloads, node-level run state, edge traversal records and existing endpoint compatibility.
- Deferred by design: loops, retries, cancellation endpoints, inbound webhooks, outbound webhooks, Vue Flow canvas builder and permission hardening are separate implementation phases.
- Red flag scan: No task uses incomplete markers or incomplete sections.
