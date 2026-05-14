from __future__ import annotations

import json
from pathlib import Path

CONTRACT_FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((CONTRACT_FIXTURES / name).read_text())


def test_incident_fixture_matches_siem_ticket_shape() -> None:
    incident = _fixture("incident.json")

    assert incident["createdAt"].endswith("Z")
    assert "updatedAt" not in incident
    assert incident["eventIds"] == ["evt_01"]
    assert incident["triageLevel"] == "T1"
    assert incident["ticketStatus"] == "new"
    assert incident["assigneeUserId"] is None
    assert incident["aiAnalysisId"] is None


def test_playbook_fixture_matches_soar_graph_shape() -> None:
    playbook = _fixture("playbook.json")

    assert "status" not in playbook
    assert "trigger" not in playbook
    assert playbook["enabled"] is False
    assert playbook["nodes"][0] == {
        "id": "trigger",
        "type": "trigger.incident_created",
        "config": {},
    }
    assert playbook["edges"][0] == {"from": "trigger", "to": "enrich_ip"}


def test_playbook_run_fixture_matches_soar_run_shape() -> None:
    run = _fixture("playbook_run.json")

    assert run["dryRun"] is True
    assert "mode" not in run
    assert "startedAt" not in run
    assert "completedAt" not in run
    assert run["createdAt"].endswith("Z")
    assert run["steps"][0]["nodeType"] == "enrich.ip"
    assert run["steps"][0]["createdAt"].endswith("Z")
