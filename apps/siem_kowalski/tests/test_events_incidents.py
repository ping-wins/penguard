from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _event_payload(
    event_type: str,
    *,
    severity: str = "medium",
    count: int | None = None,
    source_ip: str = "192.0.2.10",
) -> dict:
    attributes = {}
    if count is not None:
        attributes["count"] = count

    return {
        "source": "fortigate",
        "eventType": event_type,
        "severity": severity,
        "occurredAt": "2026-05-08T12:00:00.000Z",
        "entities": {"sourceIp": source_ip, "username": "analyst"},
        "attributes": attributes,
    }


def test_post_events_stores_event_with_generated_id_and_detects_network_scan():
    response = client.post("/events", json=_event_payload("network.scan", source_ip="192.0.2.77"))

    assert response.status_code == 200
    event = response.json()
    assert event["id"].startswith("evt_")
    assert event["eventType"] == "network.scan"

    incidents = client.get("/incidents", params={"severity": "high"}).json()
    matching = [
        incident
        for incident in incidents
        if incident["title"] == "Possible port scan" and event["id"] in incident["eventIds"]
    ]
    assert matching
    assert matching[0]["source"] == "kowalski"
    assert matching[0]["status"] == "open"
    assert matching[0]["entities"]["sourceIp"] == "192.0.2.77"
    assert matching[0]["timeline"]


def test_detection_thresholds_create_expected_incidents():
    deny = client.post("/events", json=_event_payload("network.deny", count=20)).json()
    login = client.post("/events", json=_event_payload("auth.failed_login", count=5)).json()
    suspicious = client.post(
        "/events",
        json=_event_payload("endpoint.suspicious_connection", source_ip="192.0.2.88"),
    ).json()
    below_threshold = client.post("/events", json=_event_payload("network.deny", count=19)).json()

    incidents = client.get("/incidents").json()

    assert any(
        incident["title"] == "Denied traffic burst" and deny["id"] in incident["eventIds"]
        for incident in incidents
    )
    assert any(
        incident["title"] == "Repeated failed login" and login["id"] in incident["eventIds"]
        for incident in incidents
    )
    assert any(
        incident["title"] == "Suspicious endpoint connection"
        and suspicious["id"] in incident["eventIds"]
        and incident["severity"] == "high"
        for incident in incidents
    )
    assert not any(below_threshold["id"] in incident["eventIds"] for incident in incidents)


def test_lists_events_newest_first_with_limit_and_event_type_filter():
    old_event = client.post("/events", json=_event_payload("custom.old")).json()
    new_event = client.post("/events", json=_event_payload("custom.new")).json()

    limited = client.get("/events", params={"limit": 1}).json()
    filtered = client.get("/events", params={"eventType": "custom.old"}).json()

    assert limited[0]["id"] == new_event["id"]
    assert [event["id"] for event in filtered] == [old_event["id"]]


def test_lists_incidents_with_status_and_severity_filters():
    event = client.post(
        "/events",
        json=_event_payload("network.scan", source_ip="192.0.2.91"),
    ).json()
    incident = next(
        incident
        for incident in client.get("/incidents", params={"severity": "high"}).json()
        if event["id"] in incident["eventIds"]
    )

    response = client.get("/incidents", params={"status": "open", "severity": "high"})

    assert response.status_code == 200
    assert any(item["id"] == incident["id"] for item in response.json())


def test_patch_incident_status_appends_timeline_item():
    event = client.post(
        "/events",
        json=_event_payload("network.scan", source_ip="192.0.2.92"),
    ).json()
    incident = next(
        incident
        for incident in client.get("/incidents").json()
        if event["id"] in incident["eventIds"]
    )

    response = client.patch(f"/incidents/{incident['id']}", json={"status": "triaged"})

    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "triaged"
    assert updated["timeline"][-1]["status"] == "triaged"


def test_incident_404s_for_missing_detail_and_patch():
    assert client.get("/incidents/inc_missing").status_code == 404
    assert client.patch("/incidents/inc_missing", json={"status": "resolved"}).status_code == 404
