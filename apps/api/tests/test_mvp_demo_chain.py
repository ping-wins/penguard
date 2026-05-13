"""End-to-end smoke test for the MVP demo chain:

    replay -> incident -> AI analyze -> AI containment -> draft playbook -> apply -> contained

The test stubs the SIEM and SOAR HTTP clients with in-memory fakes so it runs
without docker compose. The AI provider stays on the deterministic scripted
adapter (the default in `Settings`) so the chain is reproducible.
"""

from typing import Any

from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import soc as soc_router


class FakeSiem:
    """Tiny in-memory SIEM that supports the subset of endpoints the gateway
    uses during the MVP demo flow.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.incidents: dict[str, dict[str, Any]] = {}
        self._inc_seq = 0
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pass_through_statuses: set[int] | None = None,
    ) -> Any:
        self.calls.append({"method": method, "path": path, "json": json, "params": params})

        if method == "POST" and path == "/events":
            return self._create_event(json or {})
        if method == "GET" and path == "/incidents":
            return list(self.incidents.values())
        if method == "GET" and path.startswith("/incidents/"):
            return self.incidents[path.rsplit("/", 1)[-1]]
        if method == "PATCH" and path.endswith("/triage"):
            ticket_id = path.split("/")[2]
            incident = self.incidents[ticket_id]
            body = json or {}
            for field in ("triageLevel", "ticketStatus", "assigneeUserId", "aiAnalysisId"):
                if field in body and body[field] is not None:
                    incident[field] = body[field]
            note = body.get("note")
            if note:
                incident.setdefault("timeline", []).append(
                    {
                        "id": f"tl_{len(incident['timeline']) + 1}",
                        "type": "note",
                        "message": note,
                        "occurredAt": "2026-05-12T00:00:00Z",
                    }
                )
            return incident
        raise AssertionError(f"unexpected SIEM call {method} {path}")

    def _create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = f"evt_{len(self.events) + 1}"
        stored = {**payload, "id": event_id}
        self.events.append(stored)
        # Mimic the real detection rules: a deny event with count>=20 creates an
        # incident, and any high-severity event creates one too.
        event_type = str(payload.get("eventType") or "")
        count = int((payload.get("attributes") or {}).get("count", 1))
        severity = str(payload.get("severity") or "informational")
        if (event_type == "network.deny" and count >= 20) or severity in {"critical", "high"}:
            self._inc_seq += 1
            incident_id = f"inc_{self._inc_seq:03d}"
            incident: dict[str, Any] = {
                "id": incident_id,
                "ruleId": "denied_traffic_burst"
                if event_type == "network.deny"
                else "high_severity_event",
                "title": payload.get("attributes", {}).get("message")
                or f"Incident from {event_type}",
                "severity": severity,
                "status": "open",
                "summary": payload.get("attributes", {}).get("message")
                or "Generated from demo replay",
                "origin": {"kind": payload.get("source") or "unknown"},
                "attributes": {
                    "source": payload.get("attributes", {}).get("source")
                    or payload.get("source")
                    or "unknown",
                    **{
                        key: payload.get("attributes", {}).get(key)
                        for key in ("demoRunId", "attackType")
                        if payload.get("attributes", {}).get(key)
                    },
                },
                "entities": payload.get("entities") or {},
                "createdAt": "2026-05-12T00:00:00Z",
                "timeline": [
                    {
                        "id": "tl_1",
                        "type": "system",
                        "message": "Incident created",
                        "occurredAt": "2026-05-12T00:00:00Z",
                    }
                ],
                "eventIds": [event_id],
                "source": "kowalski",
                "triageLevel": "T1" if severity in {"critical", "high"} else "T2",
                "ticketStatus": "new",
                "assigneeUserId": None,
                "aiAnalysisId": None,
            }
            self.incidents[incident_id] = incident
        return stored


class FakeSoar:
    def __init__(self) -> None:
        self.playbooks: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self._run_seq = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pass_through_statuses: set[int] | None = None,
    ) -> Any:
        self.calls.append({"method": method, "path": path, "json": json})

        if method == "POST" and path == "/playbooks":
            pb = dict(json or {})
            self.playbooks[pb["id"]] = pb
            return pb
        if method == "POST" and path.endswith("/simulate"):
            playbook_id = path.split("/")[2]
            pb = self.playbooks[playbook_id]
            return {
                "dryRun": True,
                "valid": True,
                "steps": [
                    {
                        "nodeId": node["id"],
                        "nodeType": node["type"],
                        "status": "waiting_approval"
                        if node["type"] == "approval.required"
                        else "completed",
                        "sensitive": node["type"] == "fortigate.recommend_block",
                    }
                    for node in pb["nodes"]
                ],
            }
        if "/playbooks/" in path and path.endswith("/run"):
            self._run_seq += 1
            playbook_id = path.split("/")[-2]
            incident_id = path.split("/")[-4]
            pb = self.playbooks[playbook_id]
            # MVP guarantees dry-run; if any approval gate exists the run pauses.
            has_approval = any(node["type"] == "approval.required" for node in pb["nodes"])
            run = {
                "id": f"run_{self._run_seq:03d}",
                "incidentId": incident_id,
                "playbookId": playbook_id,
                "dryRun": True,
                "status": "waiting_approval" if has_approval else "completed",
                "steps": [],
                "createdAt": "2026-05-12T00:00:00Z",
            }
            self.runs[run["id"]] = run
            return run
        if method == "POST" and path.startswith("/playbook-runs/") and path.endswith("/approve"):
            run_id = path.split("/")[2]
            run = self.runs[run_id]
            run = {
                **run,
                "status": "completed",
            }
            self.runs[run_id] = run
            return run
        raise AssertionError(f"unexpected SOAR call {method} {path}")


def _stub_user() -> dict[str, Any]:
    return {
        "id": "usr_demo",
        "email": "demo@fortidashboard.local",
        "displayName": "Demo",
        "roles": ["analyst"],
    }


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrfToken"]}


def test_mvp_demo_chain_runs_end_to_end():
    siem = FakeSiem()
    soar = FakeSoar()
    soc_router.get_ai_provider.cache_clear()
    app.dependency_overrides[soc_router.get_siem_client] = lambda: siem
    app.dependency_overrides[soc_router.get_soar_client] = lambda: soar
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _stub_user
    app.dependency_overrides[auth_dependencies.require_admin_user] = _stub_user
    client = TestClient(app)
    audit = auth_dependencies.get_auth_audit_store()

    try:
        # Phase 1 — replay synthetic incident
        replay = client.post("/api/soc/demo/replay", headers=_csrf(client))
        assert replay.status_code == 200, replay.text
        replay_payload = replay.json()
        assert replay_payload["eventCount"] == 3
        assert len(siem.incidents) >= 1  # at least one incident raised

        ticket_id = next(iter(siem.incidents))

        # Phase 2 — list tickets and patch one through the gateway
        tickets = client.get("/api/soc/tickets")
        assert tickets.status_code == 200
        items = tickets.json()["items"]
        assert any(t["id"] == ticket_id for t in items)
        assert items[0]["triageLevel"] in {"T1", "T2", "T3"}
        assert items[0]["source"] == "kowalski"
        assert items[0]["origin"]["kind"] == "demo.replay"
        assert items[0]["attributes"]["demoRunId"] == replay_payload["demoRunId"]

        # Phase 3 — analyze + suggest containment
        analyze = client.post(
            f"/api/soc/incidents/{ticket_id}/analyze",
            headers=_csrf(client),
        )
        assert analyze.status_code == 200, analyze.text
        analysis = analyze.json()
        assert analysis["incidentId"] == ticket_id
        assert analysis["suggestedTriage"] in {"T1", "T2", "T3"}
        assert analysis["provider"] == "scripted"
        assert siem.incidents[ticket_id]["aiAnalysisId"] == analysis["id"]

        containment = client.post(
            f"/api/soc/incidents/{ticket_id}/containment-suggestions",
            headers=_csrf(client),
        )
        assert containment.status_code == 200, containment.text
        containment_payload = containment.json()
        assert containment_payload["provider"] == "scripted"
        assert len(containment_payload["steps"]) >= 1

        # Phase 4 — draft + apply playbook
        draft = client.post(
            f"/api/soc/tickets/{ticket_id}/draft-playbook",
            headers=_csrf(client),
        )
        assert draft.status_code == 201, draft.text
        draft_payload = draft.json()
        playbook_id = draft_payload["playbook"]["id"]
        assert draft_payload["simulation"]["valid"] is True
        assert playbook_id in soar.playbooks

        apply_response = client.post(
            f"/api/soc/tickets/{ticket_id}/apply-containment",
            headers={**_csrf(client), "Content-Type": "application/json"},
            json={"playbookId": playbook_id},
        )
        assert apply_response.status_code == 200, apply_response.text
        apply_payload = apply_response.json()
        assert apply_payload["playbookId"] == playbook_id
        # The AI scripted plan flags one step as sensitive, which inserts an
        # approval node and pauses the run. Either contained or paused is OK,
        # but the audit trail and ticket state must agree.
        assert apply_payload["ticketStatus"] in {"contained", "investigating"}
        assert siem.incidents[ticket_id]["ticketStatus"] == apply_payload["ticketStatus"]

        if apply_payload["ticketStatus"] == "investigating":
            approve_response = client.post(
                f"/api/soc/playbook-runs/{apply_payload['run']['id']}/approve",
                headers=_csrf(client),
            )
            assert approve_response.status_code == 200, approve_response.text
            approve_payload = approve_response.json()
            assert approve_payload["status"] == "completed"
            assert approve_payload["ticketUpdate"]["status"] == "contained"
            assert siem.incidents[ticket_id]["ticketStatus"] == "contained"

        # Audit trail must record every link in the chain.
        actions = {row["action"] for row in audit.list_events()["items"]}
        for required in (
            "soc.demo.replay",
            "soc.incident.analyzed",
            "soc.incident.containment_suggested",
            "soc.ticket.playbook_drafted",
        ):
            assert required in actions, f"missing audit action {required}"
        assert "soc.ticket.contained" in actions or "soc.ticket.containment_paused" in actions
    finally:
        app.dependency_overrides.pop(soc_router.get_siem_client, None)
        app.dependency_overrides.pop(soc_router.get_soar_client, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(auth_dependencies.require_admin_user, None)
        soc_router.get_ai_provider.cache_clear()
