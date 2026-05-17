from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import soc


class RoutingSocClient:
    def __init__(self, routes: dict[tuple[str, str], dict]) -> None:
        self.routes = routes
        self.calls: list[dict] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json=None,
        params=None,
        headers=None,
        pass_through_statuses=None,
    ) -> dict:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "headers": headers,
                "pass_through_statuses": pass_through_statuses,
            }
        )
        key = (method, path)
        if key not in self.routes:
            raise AssertionError(f"unexpected SOC request {method} {path}")
        return self.routes[key]


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    app.dependency_overrides.clear()


def test_playbook_run_executes_case_note_audit_note_and_discord_webhook_effects():
    sent: list[dict] = []

    class Sender:
        def __call__(self, url: str, payload: dict, timeout_seconds: float) -> dict:
            sent.append({"url": url, "payload": payload, "timeout": timeout_seconds})
            return {"statusCode": 204, "ok": True}

    destination_service = soc.create_playbook_webhook_destination_service(sender=Sender())
    destination = destination_service.create(
        owner_user_id="usr_01",
        name="SOC Discord",
        kind="discord",
        url="https://discord.com/api/webhooks/123456789/secret-token",
    )
    playbook = {
        "id": "pb_discord_notify",
        "name": "Discord Notify",
        "enabled": False,
        "nodes": [
            {"id": "trigger", "type": "trigger.incident_created", "config": {}},
            {
                "id": "enrich_source",
                "type": "enrich.ip",
                "config": {"field": "entities.sourceIp"},
            },
            {
                "id": "note",
                "type": "case.note",
                "config": {
                    "template": "Investigate {incident.id} from {entities.sourceIp}."
                },
            },
            {
                "id": "audit",
                "type": "audit.note",
                "config": {"message": "Discord notification requested for {incident.id}."},
            },
            {
                "id": "discord",
                "type": "notify.webhook",
                "config": {
                    "destinationId": destination["id"],
                    "content": "Critical incident {incident.id} from {entities.sourceIp}",
                },
            },
        ],
        "edges": [
            {"from": "trigger", "to": "enrich_source"},
            {"from": "enrich_source", "to": "note"},
            {"from": "note", "to": "audit"},
            {"from": "audit", "to": "discord"},
        ],
    }
    run = {
        "id": "run_discord",
        "incidentId": "inc_01",
        "playbookId": "pb_discord_notify",
        "status": "completed",
        "steps": [
            {"nodeId": node["id"], "nodeType": node["type"], "status": "completed"}
            for node in playbook["nodes"]
        ],
    }
    incident = {
        "id": "inc_01",
        "title": "Allowed port scan",
        "severity": "critical",
        "ticketStatus": "new",
        "entities": {"sourceIp": "192.0.2.50"},
        "attributes": {},
    }
    fake_soar = RoutingSocClient(
        {
            ("POST", "/incidents/inc_01/playbooks/pb_discord_notify/run"): run,
            ("GET", "/playbooks/pb_discord_notify"): playbook,
        }
    )
    fake_siem = RoutingSocClient(
        {
            ("GET", "/incidents/inc_01"): incident,
            ("PATCH", "/incidents/inc_01/triage"): {
                **incident,
                "timeline": [{"message": "Investigate inc_01 from 192.0.2.50."}],
            },
        }
    )
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.get_playbook_webhook_destination_service] = (
        lambda: destination_service
    )

    client = TestClient(app)
    response = client.post(
        "/api/soc/incidents/inc_01/playbooks/pb_discord_notify/run",
        headers=csrf_headers(client),
        json={"mode": "live"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "run_discord"
    assert [effect["nodeType"] for effect in body["effects"]] == [
        "enrich.ip",
        "case.note",
        "audit.note",
        "notify.webhook",
    ]
    assert body["effects"][0]["output"] == {
        "field": "entities.sourceIp",
        "value": "192.0.2.50",
    }
    assert fake_siem.calls[-1]["json"] == {
        "note": "Investigate inc_01 from 192.0.2.50."
    }
    assert sent == [
        {
            "url": "https://discord.com/api/webhooks/123456789/secret-token",
            "payload": {"content": "Critical incident inc_01 from 192.0.2.50"},
            "timeout": 5.0,
        }
    ]
    assert "secret-token" not in str(body)

    audit_note = auth_dependencies.get_auth_audit_store().list_events(
        action="soc.playbook.audit_note"
    )
    assert audit_note["items"][0]["details"]["message"] == (
        "Discord notification requested for inc_01."
    )


def test_playbook_run_condition_node_stops_false_branch_before_webhook():
    sent: list[dict] = []

    class Sender:
        def __call__(self, url: str, payload: dict, timeout_seconds: float) -> dict:
            sent.append({"url": url, "payload": payload, "timeout": timeout_seconds})
            return {"statusCode": 204, "ok": True}

    destination_service = soc.create_playbook_webhook_destination_service(sender=Sender())
    destination = destination_service.create(
        owner_user_id="usr_01",
        name="SOC Discord",
        kind="discord",
        url="https://discord.com/api/webhooks/123456789/secret-token",
    )
    playbook = {
        "id": "pb_low_only",
        "name": "Low only",
        "enabled": False,
        "nodes": [
            {"id": "trigger", "type": "trigger.incident_created", "config": {}},
            {
                "id": "severity",
                "type": "condition.severity",
                "config": {"severity": ["low"]},
            },
            {
                "id": "discord",
                "type": "notify.webhook",
                "config": {
                    "destinationId": destination["id"],
                    "content": "Low incident {incident.id}",
                },
            },
        ],
        "edges": [
            {"from": "trigger", "to": "severity"},
            {"from": "severity", "to": "discord", "condition": "true"},
        ],
    }
    run = {
        "id": "run_low",
        "incidentId": "inc_critical",
        "playbookId": "pb_low_only",
        "status": "completed",
        "steps": [
            {"nodeId": node["id"], "nodeType": node["type"], "status": "completed"}
            for node in playbook["nodes"]
        ],
    }
    incident = {
        "id": "inc_critical",
        "title": "Critical incident",
        "severity": "critical",
        "entities": {},
        "attributes": {},
    }
    fake_soar = RoutingSocClient(
        {
            ("POST", "/incidents/inc_critical/playbooks/pb_low_only/run"): run,
            ("GET", "/playbooks/pb_low_only"): playbook,
        }
    )
    fake_siem = RoutingSocClient({("GET", "/incidents/inc_critical"): incident})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.get_playbook_webhook_destination_service] = (
        lambda: destination_service
    )

    client = TestClient(app)
    response = client.post(
        "/api/soc/incidents/inc_critical/playbooks/pb_low_only/run",
        headers=csrf_headers(client),
        json={"mode": "live"},
    )

    assert response.status_code == 200
    assert response.json()["effects"] == [
        {
            "nodeId": "severity",
            "nodeType": "condition.severity",
            "status": "skipped",
            "output": {"matched": False, "incidentSeverity": "critical"},
        }
    ]
    assert sent == []
