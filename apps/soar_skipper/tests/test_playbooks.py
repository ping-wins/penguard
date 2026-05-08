from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_default_playbooks_are_disabled_and_available():
    response = client.get("/playbooks")

    assert response.status_code == 200
    playbooks = response.json()
    playbook_ids = {playbook["id"] for playbook in playbooks}
    assert {"pb_port_scan_triage", "pb_suspicious_endpoint_triage"} <= playbook_ids
    assert all(playbook["enabled"] is False for playbook in playbooks)


def test_create_playbook_rejects_unknown_node_type():
    response = client.post(
        "/playbooks",
        json={
            "id": "pb_unknown_node",
            "name": "Unknown node",
            "enabled": False,
            "nodes": [{"id": "unsafe", "type": "shell.exec", "config": {}}],
            "edges": [],
        },
    )

    assert response.status_code == 422


def test_create_and_get_playbook_with_allowed_nodes():
    response = client.post(
        "/playbooks",
        json={
            "id": "pb_allowed_nodes",
            "name": "Allowed nodes",
            "enabled": False,
            "nodes": [
                {"id": "trigger", "type": "trigger.incident_created", "config": {}},
                {"id": "note", "type": "case.note", "config": {"template": "Review incident"}},
            ],
            "edges": [{"from": "trigger", "to": "note"}],
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "pb_allowed_nodes"

    get_response = client.get("/playbooks/pb_allowed_nodes")
    assert get_response.status_code == 200
    assert get_response.json()["nodes"][1]["type"] == "case.note"


def test_simulate_returns_dry_run_valid_ordered_step_preview():
    response = client.post("/playbooks/pb_port_scan_triage/simulate")

    assert response.status_code == 200
    body = response.json()
    assert body["dryRun"] is True
    assert body["valid"] is True
    assert [step["nodeId"] for step in body["steps"]] == [
        "trigger",
        "severity",
        "enrich_source_ip",
        "approval",
        "recommend_block",
    ]
    assert body["steps"][-1]["sensitive"] is True
    assert body["steps"][-1]["status"] == "waiting_approval"


def test_run_creates_dry_run_history_and_waits_for_sensitive_approval():
    response = client.post("/incidents/inc_123/playbooks/pb_port_scan_triage/run")

    assert response.status_code == 201
    body = response.json()
    assert body["incidentId"] == "inc_123"
    assert body["playbookId"] == "pb_port_scan_triage"
    assert body["dryRun"] is True
    assert body["status"] == "waiting_approval"
    assert [step["status"] for step in body["steps"]] == [
        "completed",
        "completed",
        "completed",
        "waiting_approval",
        "waiting_approval",
    ]

    get_response = client.get(f"/playbook-runs/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_run_without_sensitive_or_approval_nodes_completes():
    create_response = client.post(
        "/playbooks",
        json={
            "id": "pb_note_only",
            "name": "Note only",
            "enabled": False,
            "nodes": [
                {"id": "trigger", "type": "trigger.incident_created", "config": {}},
                {"id": "note", "type": "case.note", "config": {"template": "Document only"}},
            ],
            "edges": [{"from": "trigger", "to": "note"}],
        },
    )
    assert create_response.status_code == 201

    response = client.post("/incidents/inc_456/playbooks/pb_note_only/run")

    assert response.status_code == 201
    body = response.json()
    assert body["dryRun"] is True
    assert body["status"] == "completed"
    assert [step["status"] for step in body["steps"]] == ["completed", "completed"]
