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
