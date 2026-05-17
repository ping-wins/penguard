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
