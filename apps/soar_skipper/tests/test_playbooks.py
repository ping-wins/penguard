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


def test_lists_playbook_node_types_for_visual_builder():
    response = client.get("/node-types")

    assert response.status_code == 200
    body = response.json()
    node_ids = {item["id"] for item in body["items"]}
    assert node_ids >= {
        "trigger.incident_created",
        "condition.severity",
        "case.note",
        "approval.required",
        "notify.webhook",
        "fortigate.recommend_block",
        "fortigate.temporary_block",
    }
    temporary_block = next(
        item for item in body["items"] if item["id"] == "fortigate.temporary_block"
    )
    assert temporary_block["category"] == "action"
    assert temporary_block["sensitive"] is True
    assert temporary_block["dryRunOnly"] is False
    assert temporary_block["executionMode"] == "approval_required"
    assert temporary_block["liveAvailable"] is True
    assert temporary_block["boundary"] == "fortigate_policy_orchestration"
    assert temporary_block["configSchema"]["required"] == [
        "scope",
        "durationMinutes",
        "sourceField",
    ]

    recommend_block = next(
        item for item in body["items"] if item["id"] == "fortigate.recommend_block"
    )
    assert recommend_block["category"] == "action"
    assert recommend_block["sensitive"] is True
    assert recommend_block["dryRunOnly"] is True
    assert recommend_block["executionMode"] == "dry_run"
    assert recommend_block["liveAvailable"] is False
    assert recommend_block["boundary"] == "recommendation_only"
    assert recommend_block["configSchema"]["required"] == ["field"]

    case_note = next(item for item in body["items"] if item["id"] == "case.note")
    assert case_note["boundary"] == "case_note"
    assert case_note["executionMode"] == "dry_run"

    webhook = next(item for item in body["items"] if item["id"] == "webhook.dry_run")
    assert webhook["boundary"] == "webhook_dry_run"
    assert webhook["dryRunOnly"] is True


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
    assert body["steps"][-1]["nodeType"] == "fortigate.temporary_block"


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
    assert [node["nodeId"] for node in body["nodeRuns"]] == [
        "trigger",
        "severity",
        "enrich_source_ip",
        "approval",
        "recommend_block",
    ]
    assert body["nodeRuns"][-1]["status"] == "waiting_approval"
    assert body["edgeTraversals"][-1]["condition"] == "success"

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


def test_list_playbook_runs_filters_by_status():
    response = client.post("/incidents/inc_789/playbooks/pb_port_scan_triage/run")
    assert response.status_code == 201

    all_runs = client.get("/playbook-runs")
    waiting_runs = client.get("/playbook-runs", params={"status": "waiting_approval"})
    completed_runs = client.get("/playbook-runs", params={"status": "completed"})

    assert all_runs.status_code == 200
    assert response.json()["id"] in {run["id"] for run in all_runs.json()}
    assert response.json()["id"] in {run["id"] for run in waiting_runs.json()}
    assert response.json()["id"] not in {run["id"] for run in completed_runs.json()}


def test_approve_playbook_run_completes_waiting_steps():
    response = client.post("/incidents/inc_approved/playbooks/pb_port_scan_triage/run")
    assert response.status_code == 201

    approve_response = client.post(f"/playbook-runs/{response.json()['id']}/approve")

    assert approve_response.status_code == 200
    body = approve_response.json()
    assert body["status"] == "completed"
    assert {step["status"] for step in body["steps"]} == {"completed"}


def test_fortiweb_recommend_block_node_is_dry_run_only():
    response = client.get("/node-types")
    assert response.status_code == 200
    nodes = {node["id"]: node for node in response.json()["items"]}
    node = nodes["fortiweb.recommend_block"]
    assert node["executionMode"] == "dry_run"
    assert node["liveAvailable"] is False
    assert node["boundary"] == "recommendation_only"
    assert node["sensitive"] is True
    assert node["configSchema"]["required"] == ["sourceIp"]
