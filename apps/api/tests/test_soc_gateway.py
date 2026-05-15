import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.csrf_dependency import require_csrf
from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.routers import lab_demo, soc
from app.soc import client as soc_client_module
from app.soc.client import SocServiceClient


class FakeSocClient:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"ok": True}
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
        return self.response


class FailingSocClient:
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
        raise HTTPException(status_code=503, detail="service unavailable")


class FakeFortiGatePolicyClient:
    def __init__(self) -> None:
        self.created_addresses: list[dict] = []
        self.created_policies: list[dict] = []

    def get_policies(self) -> list[dict]:
        return [{"name": "FD_LAB_ALLOW_SCAN", "policyid": 10}]

    def get_address_objects(self) -> list[dict]:
        return []

    def create_address_object(self, *, name: str, subnet: str, comment: str) -> dict:
        payload = {"name": name, "subnet": subnet, "comment": comment}
        self.created_addresses.append(payload)
        return {"status": "success", "mkey": name}

    def create_firewall_policy(self, payload: dict) -> dict:
        self.created_policies.append(dict(payload))
        return {"status": "success", "mkey": payload["name"]}


class FakeFortiGatePolicyService:
    def __init__(self, client: FakeFortiGatePolicyClient) -> None:
        self.client = client

    def get_policy_client(self, *, integration_id: str, owner_user_id: str):
        _ = (integration_id, owner_user_id)
        return self.client


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _user_with_roles(*roles: str) -> dict:
    return {
        "id": "usr_test",
        "email": "test@example.com",
        "displayName": "Test User",
        "roles": list(roles),
    }


def _enable_lab_demo_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS", "true")
    get_settings.cache_clear()


def test_demo_replay_is_not_available_by_default():
    get_settings.cache_clear()
    client = TestClient(app)
    fake_siem = FakeSocClient({"id": "evt_01"})
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: _user_with_roles(
        "admin"
    )

    response = client.post("/api/soc/demo/replay", headers=csrf_headers(client))

    assert response.status_code == 404
    assert fake_siem.calls == []


def test_lab_demo_router_can_be_mounted_explicitly_for_lab_runs(monkeypatch):
    _enable_lab_demo_tools(monkeypatch)
    fake_siem = FakeSocClient({"id": "evt_01"})
    client = TestClient(_lab_demo_test_app(fake_siem, _user_with_roles("admin")))

    response = client.post("/api/soc/demo/replay")

    assert response.status_code == 200
    assert response.json()["eventCount"] == 3
    assert [call["path"] for call in fake_siem.calls] == ["/events", "/events", "/events"]


def test_demo_replay_rejects_non_admin_analysts(monkeypatch):
    _enable_lab_demo_tools(monkeypatch)
    fake_siem = FakeSocClient({"id": "evt_01"})
    client = TestClient(_lab_demo_test_app(fake_siem, _user_with_roles("analyst")))

    response = client.post("/api/soc/demo/replay")

    assert response.status_code == 403
    assert fake_siem.calls == []


def test_demo_replay_allows_admin_users(monkeypatch):
    _enable_lab_demo_tools(monkeypatch)
    fake_siem = FakeSocClient({"id": "evt_01"})
    client = TestClient(_lab_demo_test_app(fake_siem, _user_with_roles("admin")))

    response = client.post("/api/soc/demo/replay")

    assert response.status_code == 200
    assert [call["path"] for call in fake_siem.calls] == ["/events", "/events", "/events"]


def _lab_demo_test_app(fake_siem: FakeSocClient, user: dict):
    from fastapi import FastAPI

    lab_app = FastAPI()
    lab_app.include_router(lab_demo.router, prefix="/api")
    lab_app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    lab_app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: user
    lab_app.dependency_overrides[require_csrf] = lambda: None
    return lab_app


def test_siem_event_gateway_forwards_payload_and_audits():
    client = TestClient(app)
    fake_siem = FakeSocClient({"id": "evt_01", "eventType": "network.scan"})
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.post(
        "/api/soc/events",
        headers=csrf_headers(client),
        json={
            "source": "fortigate",
            "eventType": "network.scan",
            "severity": "high",
            "occurredAt": "2026-05-08T12:00:00.000Z",
            "entities": {"sourceIp": "192.0.2.10"},
            "attributes": {},
        },
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.event.created")

    assert response.status_code == 200
    assert response.json()["id"] == "evt_01"
    assert fake_siem.calls == [
        {
            "method": "POST",
            "path": "/events",
            "json": {
                "source": "fortigate",
                "eventType": "network.scan",
                "severity": "high",
                "occurredAt": "2026-05-08T12:00:00.000Z",
                "entities": {"sourceIp": "192.0.2.10"},
                "attributes": {},
            },
            "params": None,
            "headers": None,
            "pass_through_statuses": None,
        }
    ]
    assert audit["items"][0]["details"]["service"] == "siem_kowalski"


def test_siem_incident_list_gateway_forwards_filters():
    client = TestClient(app)
    fake_siem = FakeSocClient({"items": []})
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.get(
        "/api/soc/incidents",
        params={"limit": 25, "status": "open", "severity": "high"},
    )

    assert response.status_code == 200
    assert fake_siem.calls[0] == {
        "method": "GET",
        "path": "/incidents",
        "json": None,
        "params": {"limit": 25, "status": "open", "severity": "high"},
        "headers": None,
        "pass_through_statuses": None,
    }


def test_siem_rule_list_gateway_forwards_to_kowalski():
    client = TestClient(app)
    fake_siem = FakeSocClient(
        {
            "items": [
                {
                    "id": "fortigate_resource_pressure",
                    "title": "FortiGate resource pressure",
                    "conditions": [],
                }
            ]
        }
    )
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.get("/api/soc/rules")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "fortigate_resource_pressure"
    assert fake_siem.calls[0] == {
        "method": "GET",
        "path": "/rules",
        "json": None,
        "params": None,
        "headers": None,
        "pass_through_statuses": None,
    }


def test_incident_endpoint_context_gateway_correlates_siem_incident_with_xdr():
    client = TestClient(app)
    incident = {
        "id": "inc_01",
        "title": "Suspicious endpoint connection",
        "severity": "high",
        "status": "open",
        "entities": {
            "sourceIp": "192.0.2.50",
            "hostname": "demo-endpoint-01",
            "username": "analyst",
        },
    }
    fake_siem = FakeSocClient(incident)
    fake_xdr = FakeSocClient(
        {
            "incidentEntities": incident["entities"],
            "items": [
                {
                    "endpoint": {"id": "end_01", "hostname": "demo-endpoint-01"},
                    "score": 100,
                    "matchedFields": [
                        {"field": "sourceIp", "value": "192.0.2.50"},
                        {"field": "hostname", "value": "demo-endpoint-01"},
                    ],
                    "timeline": [],
                }
            ],
            "total": 1,
        }
    )
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.get(
        "/api/soc/incidents/inc_01/endpoint-context",
        params={"limit": 3},
    )

    assert response.status_code == 200
    assert fake_siem.calls[0]["path"] == "/incidents/inc_01"
    assert fake_xdr.calls[0] == {
        "method": "POST",
        "path": "/correlations/endpoint-context",
        "json": {"entities": incident["entities"], "limit": 3},
        "params": None,
        "headers": None,
        "pass_through_statuses": None,
    }
    body = response.json()
    assert body["incidentId"] == "inc_01"
    assert body["incident"] == incident
    assert body["total"] == 1
    assert body["items"][0]["endpoint"]["id"] == "end_01"


def test_endpoint_related_incidents_matches_endpoint_identity_and_excludes_unrelated():
    client = TestClient(app)
    endpoint = {
        "id": "end_win_dc01",
        "hostname": "WIN-SOC-DC01",
        "ipAddresses": ["192.0.2.10", "10.0.2.15"],
        "currentUser": "FORTIDASHBOARD\\felipe",
        "attributes": {"os": "Windows"},
    }
    incidents = [
        {
            "id": "inc_endpoint_id",
            "title": "Endpoint id match",
            "severity": "high",
            "triageLevel": "T1",
            "ticketStatus": "new",
            "entities": {"endpointId": "end_win_dc01"},
        },
        {
            "id": "inc_hostname_ip",
            "title": "Hostname and IP match",
            "severity": "medium",
            "triageLevel": "T2",
            "ticketStatus": "investigating",
            "entities": {"hostname": "win-soc-dc01", "sourceIp": "192.0.2.10"},
        },
        {
            "id": "inc_user_principal",
            "title": "Principal match",
            "severity": "low",
            "triageLevel": "T3",
            "ticketStatus": "new",
            "entities": {"username": "felipe@fortidashboard.local"},
        },
        {
            "id": "inc_unrelated",
            "title": "Other endpoint",
            "severity": "critical",
            "triageLevel": "T1",
            "ticketStatus": "new",
            "entities": {
                "endpointId": "end_linux_01",
                "hostname": "linux-01",
                "sourceIp": "198.51.100.20",
                "username": "other",
            },
        },
    ]
    fake_xdr = FakeSocClient(endpoint)
    fake_siem = FakeSocClient({"items": incidents, "total": len(incidents)})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.get("/api/weapons/endpoints/end_win_dc01/related-incidents")

    assert response.status_code == 200
    assert fake_xdr.calls[0]["path"] == "/endpoints/end_win_dc01"
    assert fake_siem.calls[0] == {
        "method": "GET",
        "path": "/incidents",
        "json": None,
        "params": {"limit": 200},
        "headers": None,
        "pass_through_statuses": None,
    }
    body = response.json()
    assert body["endpointId"] == "end_win_dc01"
    assert [item["id"] for item in body["items"]] == [
        "inc_endpoint_id",
        "inc_hostname_ip",
        "inc_user_principal",
    ]
    assert body["total"] == 3
    assert body["matchedFields"] == {
        "inc_endpoint_id": ["endpointId"],
        "inc_hostname_ip": ["hostname", "sourceIp"],
        "inc_user_principal": ["username"],
    }


def test_soar_playbook_run_gateway_forwards_and_audits():
    client = TestClient(app)
    fake_soar = FakeSocClient({"id": "pbr_01", "status": "waiting_approval"})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar

    response = client.post(
        "/api/soc/incidents/inc_01/playbooks/pb_01/run",
        headers=csrf_headers(client),
        json={"mode": "dry_run"},
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.playbook.run_created")

    assert response.status_code == 200
    assert response.json()["id"] == "pbr_01"
    assert fake_soar.calls[0]["path"] == "/incidents/inc_01/playbooks/pb_01/run"
    assert fake_soar.calls[0]["json"] == {"mode": "dry_run"}
    assert audit["items"][0]["details"]["runId"] == "pbr_01"


def test_soar_node_types_gateway_forwards_builder_catalog():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "items": [
                {
                    "id": "case.note",
                    "label": "Case Note",
                    "category": "action",
                    "sensitive": False,
                    "dryRunOnly": True,
                    "executionMode": "dry_run",
                    "liveAvailable": False,
                    "boundary": "case_note",
                    "configSchema": {"type": "object"},
                }
            ]
        }
    )
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar

    response = client.get("/api/soc/playbook-node-types")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "case.note"
    assert fake_soar.calls[0] == {
        "method": "GET",
        "path": "/node-types",
        "json": None,
        "params": None,
        "headers": None,
        "pass_through_statuses": None,
    }


def test_ai_firewall_steps_map_to_fortigate_temporary_block():
    assert soc._map_ai_step_to_soar_node("firewall.block_ip") == (
        "fortigate.temporary_block",
        True,
    )
    assert soc._map_ai_step_to_soar_node("fortigate.recommend_block") == (
        "fortigate.temporary_block",
        True,
    )


def test_soar_playbook_run_approve_requires_admin():
    client = TestClient(app)
    fake_soar = FakeSocClient({"id": "pbr_01", "status": "completed"})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar

    response = client.post(
        "/api/soc/playbook-runs/pbr_01/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    assert fake_soar.calls == []


def test_soar_playbook_run_approve_forwards_and_audits_for_admin():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "pbr_01",
            "incidentId": "inc_01",
            "playbookId": "pb_01",
            "status": "completed",
        }
    )
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "roles": ["admin"],
    }

    response = client.post(
        "/api/soc/playbook-runs/pbr_01/approve",
        headers=csrf_headers(client),
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.playbook_run.approved")

    assert response.status_code == 200
    assert fake_soar.calls[0]["path"] == "/playbook-runs/pbr_01/approve"
    assert audit["items"][0]["actor"]["id"] == "usr_admin"
    assert audit["items"][0]["details"]["runId"] == "pbr_01"


def test_soar_playbook_run_approve_marks_completed_incident_contained():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "pbr_01",
            "incidentId": "inc_01",
            "playbookId": "pb_01",
            "status": "completed",
        }
    )
    fake_siem = FakeSocClient({"id": "inc_01", "ticketStatus": "contained"})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "roles": ["admin"],
    }

    response = client.post(
        "/api/soc/playbook-runs/pbr_01/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["ticketUpdate"] == {
        "status": "contained",
        "incidentId": "inc_01",
        "ticket": {"id": "inc_01", "ticketStatus": "contained"},
    }
    assert fake_siem.calls == [
        {
            "method": "PATCH",
            "path": "/incidents/inc_01/triage",
            "json": {
                "ticketStatus": "contained",
                "note": "Playbook run pbr_01 approved and completed containment.",
            },
            "params": None,
            "headers": None,
            "pass_through_statuses": None,
        }
    ]
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.playbook_run.approved")
    assert audit["items"][0]["outcome"] == "success"
    assert audit["items"][0]["details"]["ticketUpdate"]["status"] == "contained"


def test_soar_playbook_run_approve_returns_partial_when_ticket_patch_fails():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "pbr_01",
            "incidentId": "inc_01",
            "playbookId": "pb_01",
            "status": "completed",
        }
    )
    fake_siem = FailingSocClient()
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "roles": ["admin"],
    }

    response = client.post(
        "/api/soc/playbook-runs/pbr_01/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["ticketUpdate"]["status"] == "failed"
    assert response.json()["ticketUpdate"]["incidentId"] == "inc_01"
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.playbook_run.approved")
    assert audit["items"][0]["outcome"] == "partial"
    assert audit["items"][0]["details"]["ticketUpdate"]["status"] == "failed"


def test_soar_playbook_run_approve_waiting_approval_keeps_current_behavior():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "pbr_01",
            "incidentId": "inc_01",
            "playbookId": "pb_01",
            "status": "waiting_approval",
        }
    )
    fake_siem = FakeSocClient({"id": "inc_01", "ticketStatus": "contained"})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "roles": ["admin"],
    }

    response = client.post(
        "/api/soc/playbook-runs/pbr_01/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert "ticketUpdate" not in response.json()
    assert fake_siem.calls == []
    audit = auth_dependencies.get_auth_audit_store().list_events(action="soc.playbook_run.approved")
    assert audit["items"][0]["outcome"] == "success"


def test_soar_playbook_run_approve_with_fortigate_policy_step_requires_policy_review():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "pbr_policy",
            "incidentId": "inc_policy",
            "playbookId": "pb_policy",
            "status": "completed",
            "steps": [
                {
                    "nodeId": "block",
                    "nodeType": "fortigate.temporary_block",
                    "status": "completed",
                    "sensitive": True,
                }
            ],
        }
    )
    fake_siem = FakeSocClient({"id": "inc_policy", "ticketStatus": "contained"})
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[soc.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "roles": ["admin"],
    }

    response = client.post(
        "/api/soc/playbook-runs/pbr_policy/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["policyReviewRequired"] is True
    assert fake_siem.calls == []


def test_playbook_run_policy_review_and_apply_link_ticket_to_fortigate_policy():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    fgt_client = FakeFortiGatePolicyClient()
    run = {
        "id": "run_123",
        "incidentId": "inc_123",
        "playbookId": "pb_123",
        "status": "completed",
        "steps": [
            {
                "id": "step_1",
                "nodeId": "block",
                "nodeType": "fortigate.temporary_block",
                "status": "completed",
                "sensitive": True,
            }
        ],
    }
    fake_soar = FakeSocClient(run)
    fake_siem = FakeSocClient({"id": "inc_123", "ticketStatus": "contained"})

    def override_policy_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    client = TestClient(app)
    app.dependency_overrides[soc.get_policy_db] = override_policy_db
    app.dependency_overrides[soc.get_fortigate_policy_service] = lambda: (
        FakeFortiGatePolicyService(fgt_client)
    )
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: _user_with_roles(
        "admin"
    )

    review_response = client.post(
        "/api/soc/playbook-runs/run_123/policy-review",
        headers=csrf_headers(client),
        json={
            "integrationId": "int_fgt_lab",
            "scope": "source_destination",
            "sourceIp": "192.0.2.50",
            "destinationIp": "198.51.100.10",
            "sourceInterface": "port2",
            "destinationInterface": "port3",
            "durationMinutes": 30,
        },
    )
    review = review_response.json()
    assert review_response.status_code == 200
    assert review["runId"] == "run_123"
    assert review["incidentId"] == "inc_123"
    assert fgt_client.created_policies == []

    apply_response = client.post(
        "/api/soc/playbook-runs/run_123/policy-apply",
        headers=csrf_headers(client),
        json={
            "integrationId": "int_fgt_lab",
            "requestId": review["request_id"],
            "reviewHash": review["review_hash"],
        },
    )

    assert apply_response.status_code == 200
    assert apply_response.json()["policy"]["status"] == "applied"
    assert apply_response.json()["ticketUpdate"] == {
        "status": "contained",
        "incidentId": "inc_123",
        "ticket": {"id": "inc_123", "ticketStatus": "contained"},
    }
    assert fgt_client.created_policies[0]["name"] == (
        "FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10"
    )
    assert fake_siem.calls[-1]["path"] == "/incidents/inc_123/triage"


def test_playbook_run_policy_review_rejects_runs_without_fortigate_policy_step():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "id": "run_note",
            "incidentId": "inc_note",
            "playbookId": "pb_note",
            "status": "completed",
            "steps": [{"nodeType": "case.note", "status": "completed"}],
        }
    )
    app.dependency_overrides[soc.get_soar_client] = lambda: fake_soar

    response = client.post(
        "/api/soc/playbook-runs/run_note/policy-review",
        headers=csrf_headers(client),
        json={
            "integrationId": "int_fgt_lab",
            "scope": "source_only",
            "sourceIp": "192.0.2.50",
            "sourceInterface": "port2",
            "destinationInterface": "port3",
            "durationMinutes": 30,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Playbook run does not contain a FortiGate temporary block step"
    }


def test_xdr_enrollment_gateway_does_not_log_token():
    client = TestClient(app)
    fake_xdr = FakeSocClient(
        {
            "id": "enr_01",
            "token": "demo-enrollment-token",
            "createdAt": "2026-05-08T12:00:00.000Z",
        }
    )
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.post(
        "/api/weapons/enrollments",
        headers=csrf_headers(client),
        json={"displayName": "Demo endpoint"},
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="xdr.enrollment.created")

    assert response.status_code == 200
    assert response.json()["token"] == "demo-enrollment-token"
    assert audit["items"][0]["details"] == {
        "enrollmentId": "enr_01",
        "service": "xdr_rico",
    }


def test_gateway_normalizes_internal_service_errors():
    client = TestClient(app)
    app.dependency_overrides[soc.get_siem_client] = lambda: FailingSocClient()

    response = client.get("/api/soc/events")

    assert response.status_code == 503
    assert response.json()["detail"] == "service unavailable"


def test_xdr_endpoint_event_gateway_forwards_enrollment_authorization():
    client = TestClient(app)
    fake_xdr = FakeSocClient({"endpoint": {"id": "end_01"}, "timelineItem": {"id": "tl_01"}})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.post(
        "/api/weapons/endpoint-events",
        headers={
            **csrf_headers(client),
            "Authorization": "Bearer demo-enrollment-token",
        },
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00.000Z",
        },
    )

    assert response.status_code == 200
    assert fake_xdr.calls[0]["headers"] == {"Authorization": "Bearer demo-enrollment-token"}
    assert fake_xdr.calls[0]["pass_through_statuses"] == {401, 403}
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="xdr.endpoint_event.created"
    )
    assert audit["items"][0]["details"]["actorType"] == "agent_private"


def test_xdr_endpoint_delete_gateway_audits_and_uses_csrf():
    client = TestClient(app)
    fake_xdr = FakeSocClient({"deleted": True, "endpointId": "end_01"})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.delete(
        "/api/weapons/endpoints/end_01",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert fake_xdr.calls == [
        {
            "method": "DELETE",
            "path": "/endpoints/end_01",
            "json": None,
            "params": None,
            "headers": None,
            "pass_through_statuses": {404},
        }
    ]
    audit = auth_dependencies.get_auth_audit_store().list_events(action="xdr.endpoint.deleted")
    assert audit["items"][0]["details"] == {
        "endpointId": "end_01",
        "service": "xdr_rico",
    }


def test_xdr_endpoint_event_gateway_adds_observed_source_ip_to_payload():
    client = TestClient(app, client=("192.168.56.10", 55088))
    fake_xdr = FakeSocClient({"endpoint": {"id": "win-server-01"}, "timelineItem": {"id": "tl_01"}})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.post(
        "/api/weapons/endpoint-events",
        headers={
            **csrf_headers(client),
            "Authorization": "Bearer demo-enrollment-token",
        },
        json={
            "endpointId": "win-server-01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-12T22:32:18.675000Z",
            "hostname": "WIN-T2D53C8JOKL",
            "ipAddresses": ["10.0.2.15", "192.168.56.10"],
            "attributes": {"service": "agent_private"},
        },
    )

    assert response.status_code == 200
    assert fake_xdr.calls[0]["json"]["attributes"] == {
        "service": "agent_private",
        "observedSourceIp": "192.168.56.10",
    }


def test_xdr_endpoint_event_gateway_forwards_windows_security_events_to_siem():
    client = TestClient(app)
    fake_xdr = FakeSocClient(
        {
            "endpoint": {"id": "end_win_dc01"},
            "timelineItem": {"id": "tl_01", "eventType": "auth.failed_login"},
        }
    )
    fake_siem = FakeSocClient({"id": "evt_01", "eventType": "auth.failed_login"})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.post(
        "/api/weapons/endpoint-events",
        headers={
            **csrf_headers(client),
            "Authorization": "Bearer demo-enrollment-token",
        },
        json={
            "endpointId": "end_win_dc01",
            "eventType": "auth.failed_login",
            "occurredAt": "2026-05-12T13:30:00.000Z",
            "hostname": "WIN-SOC-DC01",
            "ipAddresses": ["192.0.2.10"],
            "currentUser": "FORTIDASHBOARD\\felipe",
            "attributes": {
                "source": "agent_private.windows_security",
                "windowsEventId": 4625,
                "count": 6,
                "sourceIp": "192.0.2.77",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["siemForwarding"] == {
        "status": "created",
        "eventCount": 1,
        "eventIds": ["evt_01"],
    }
    assert fake_siem.calls == [
        {
            "method": "POST",
            "path": "/events",
            "json": {
                "source": "xdr_rico.agent_private",
                "eventType": "auth.failed_login",
                "severity": "medium",
                "occurredAt": "2026-05-12T13:30:00.000Z",
                "entities": {
                    "endpointId": "end_win_dc01",
                    "hostname": "WIN-SOC-DC01",
                    "username": "FORTIDASHBOARD\\felipe",
                    "sourceIp": "192.0.2.77",
                },
                "attributes": {
                    "source": "agent_private.windows_security",
                    "windowsEventId": 4625,
                    "count": 6,
                    "sourceIp": "192.0.2.77",
                    "observedSourceIp": "testclient",
                    "xdrTimelineItemId": "tl_01",
                },
            },
            "params": None,
            "headers": None,
            "pass_through_statuses": None,
        }
    ]


def test_xdr_endpoint_event_gateway_forwards_suspicious_process_to_suspicious_connection_siem():
    client = TestClient(app, client=("192.0.2.50", 55088))
    fake_xdr = FakeSocClient(
        {
            "endpoint": {"id": "demo-endpoint-01"},
            "timelineItem": {"id": "tl_suspicious_01", "eventType": "suspicious.process"},
        }
    )
    fake_siem = FakeSocClient({"id": "evt_suspicious_01"})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.post(
        "/api/weapons/endpoint-events",
        headers={
            **csrf_headers(client),
            "Authorization": "Bearer demo-enrollment-token",
        },
        json={
            "endpointId": "demo-endpoint-01",
            "eventType": "suspicious.process",
            "occurredAt": "2026-05-12T13:35:00.000Z",
            "hostname": "demo-endpoint-01",
            "ipAddresses": ["192.0.2.50"],
            "currentUser": "SOC-DEMO\\analyst",
            "attributes": {
                "source": "simulator",
                "process": "curl",
                "remoteIp": "198.51.100.20",
                "reason": "unexpected outbound beacon pattern",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["siemForwarding"]["status"] == "created"
    assert fake_siem.calls[0]["json"] == {
        "source": "xdr_rico.agent_private",
        "eventType": "endpoint.suspicious_connection",
        "severity": "high",
        "occurredAt": "2026-05-12T13:35:00.000Z",
        "entities": {
            "endpointId": "demo-endpoint-01",
            "hostname": "demo-endpoint-01",
            "username": "SOC-DEMO\\analyst",
            "sourceIp": "192.0.2.50",
            "destinationIp": "198.51.100.20",
        },
        "attributes": {
            "source": "simulator",
            "process": "curl",
            "remoteIp": "198.51.100.20",
            "reason": "unexpected outbound beacon pattern",
            "observedSourceIp": "192.0.2.50",
            "originKind": "xdr.endpoint_event",
            "originSource": "simulator",
            "xdrTimelineItemId": "tl_suspicious_01",
        },
    }


def test_xdr_endpoint_event_gateway_forwards_suspicious_connection_snapshot_to_siem():
    client = TestClient(app, client=("192.0.2.50", 55088))
    fake_xdr = FakeSocClient(
        {
            "endpoint": {"id": "demo-endpoint-01"},
            "timelineItem": {"id": "tl_conn_01", "eventType": "connection.snapshot"},
        }
    )
    fake_siem = FakeSocClient({"id": "evt_conn_01"})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem

    response = client.post(
        "/api/weapons/endpoint-events",
        headers={
            **csrf_headers(client),
            "Authorization": "Bearer demo-enrollment-token",
        },
        json={
            "endpointId": "demo-endpoint-01",
            "eventType": "connection.snapshot",
            "occurredAt": "2026-05-12T13:35:00.000Z",
            "hostname": "demo-endpoint-01",
            "ipAddresses": ["192.0.2.50"],
            "attributes": {
                "source": "agent_private.connection_snapshot",
                "connections": [
                    {
                        "remoteIp": "198.51.100.20",
                        "remotePort": 443,
                        "state": "established",
                        "suspicious": True,
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    assert fake_siem.calls[0]["json"]["eventType"] == "endpoint.suspicious_connection"
    assert fake_siem.calls[0]["json"]["entities"]["destinationIp"] == "198.51.100.20"
    assert fake_siem.calls[0]["json"]["attributes"]["originSource"] == (
        "agent_private.connection_snapshot"
    )


def test_xdr_endpoint_event_gateway_requires_enrollment_authorization():
    client = TestClient(app)
    fake_xdr = FakeSocClient({"ok": True})
    app.dependency_overrides[soc.get_xdr_client] = lambda: fake_xdr

    response = client.post(
        "/api/weapons/endpoint-events",
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00.000Z",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Endpoint enrollment token required"
    assert fake_xdr.calls == []


def test_service_client_wraps_internal_list_payloads(monkeypatch):
    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        return Response(200, json=[{"id": "inc_01"}])

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)

    client = SocServiceClient(
        base_url="http://siem-kowalski:8000",
        service_name="siem_kowalski",
        timeout_seconds=1.0,
    )

    assert client.request("GET", "/incidents") == {"items": [{"id": "inc_01"}]}


def test_service_client_logs_request_result_without_auth_secrets(monkeypatch, caplog):
    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        assert headers == {"Authorization": "Bearer secret-enrollment-token"}
        assert params == {"limit": 10, "token": "secret-query-token"}
        return Response(200, json={"items": []})

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)
    caplog.set_level("INFO", logger="uvicorn.error")
    client = SocServiceClient(
        base_url="http://xdr-rico:8000",
        service_name="xdr_rico",
        timeout_seconds=1.0,
    )

    assert client.request(
        "GET",
        "/endpoints",
        params={"limit": 10, "token": "secret-query-token"},
        headers={"Authorization": "Bearer secret-enrollment-token"},
    ) == {"items": []}

    assert (
        "soc_service_request service=xdr_rico method=GET path=/endpoints attempt=1/2" in caplog.text
    )
    assert (
        "soc_service_response service=xdr_rico method=GET path=/endpoints "
        "status_code=200 item_count=0"
    ) in caplog.text
    assert "secret-enrollment-token" not in caplog.text
    assert "secret-query-token" not in caplog.text
    assert "token=<redacted>" in caplog.text
    assert "Authorization" not in caplog.text


def test_service_client_can_pass_through_selected_internal_statuses(monkeypatch):
    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        return Response(401, json={"detail": "token rejected"})

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)

    client = SocServiceClient(
        base_url="http://xdr-rico:8000",
        service_name="xdr_rico",
        timeout_seconds=1.0,
    )

    with pytest.raises(HTTPException) as exc_info:
        client.request("POST", "/endpoint-events", pass_through_statuses={401})

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "token rejected"


def test_service_client_retries_request_errors(monkeypatch):
    calls = 0

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise soc_client_module.httpx.RequestError("connection reset")
        return Response(200, json={"ok": True})

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)
    client = SocServiceClient(
        base_url="http://siem-kowalski:8000",
        service_name="siem_kowalski",
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_seconds=0.0,
    )

    assert client.request("GET", "/events") == {"ok": True}
    assert calls == 2


def test_service_client_retries_5xx_responses(monkeypatch):
    responses = [
        Response(502, json={"detail": "bad gateway"}),
        Response(200, json={"ok": True}),
    ]

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)
    client = SocServiceClient(
        base_url="http://siem-kowalski:8000",
        service_name="siem_kowalski",
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_seconds=0.0,
    )

    assert client.request("GET", "/events") == {"ok": True}
    assert responses == []


def test_service_client_does_not_retry_422_responses(monkeypatch):
    calls = 0

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        nonlocal calls
        calls += 1
        return Response(422, json={"detail": "validation failed"})

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)
    client = SocServiceClient(
        base_url="http://siem-kowalski:8000",
        service_name="siem_kowalski",
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_seconds=0.0,
    )

    with pytest.raises(HTTPException) as exc_info:
        client.request("GET", "/events")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid request for siem_kowalski"
    assert calls == 1


@pytest.mark.parametrize(
    ("internal_status", "external_status", "detail"),
    [
        (401, 502, "siem_kowalski rejected gateway credentials"),
        (403, 502, "siem_kowalski rejected gateway credentials"),
        (422, 400, "Invalid request for siem_kowalski"),
        (429, 503, "siem_kowalski is temporarily rate limited"),
        (500, 502, "siem_kowalski returned an upstream error"),
    ],
)
def test_service_client_normalizes_internal_error_payloads(
    monkeypatch,
    internal_status,
    external_status,
    detail,
):
    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        return Response(internal_status, json={"detail": "internal stack or auth detail"})

    monkeypatch.setattr(soc_client_module.httpx, "request", fake_request)
    client = SocServiceClient(
        base_url="http://siem-kowalski:8000",
        service_name="siem_kowalski",
        timeout_seconds=1.0,
    )

    with pytest.raises(HTTPException) as exc_info:
        client.request("GET", "/events")

    assert exc_info.value.status_code == external_status
    assert exc_info.value.detail == detail
