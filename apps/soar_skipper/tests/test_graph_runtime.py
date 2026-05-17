from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Playbook, PlaybookEdge, PlaybookNode
from app.runtime import build_playbook_run, build_step_previews, ordered_nodes


def test_validate_playbook_for_save_requires_trigger():
    from app.graph_validation import validate_playbook_for_save

    playbook = Playbook(
        id="pb_no_trigger",
        name="No trigger",
        nodes=[PlaybookNode(id="note", type="case.note")],
    )

    errors = validate_playbook_for_save(playbook)

    assert errors == ["playbook must include at least one trigger node"]


def test_validate_playbook_for_save_accepts_default_playbook_shape():
    from app.graph_validation import validate_playbook_for_save

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
