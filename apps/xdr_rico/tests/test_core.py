from fastapi.testclient import TestClient

from app.main import app, reset_state


def client() -> TestClient:
    reset_state()
    return TestClient(app)


def enrollment_headers(test_client: TestClient) -> dict[str, str]:
    response = test_client.post("/enrollments", json={"displayName": "Demo endpoint"})
    return {"Authorization": f"Bearer {response.json()['token']}"}


def clear_legacy_memory_maps() -> None:
    store = app.state.xdr_store
    for attr in ("enrollments", "endpoints", "timeline"):
        value = getattr(store, attr, None)
        if isinstance(value, dict):
            value.clear()


def test_enrollment_token_is_returned_once_and_not_persisted_in_plaintext():
    test_client = client()

    response = test_client.post("/enrollments", json={"displayName": "Demo laptop"})

    assert response.status_code == 201
    body = response.json()
    assert body["displayName"] == "Demo laptop"
    assert body["token"].startswith("xdr_enroll_")
    assert "tokenHash" not in body

    second_response = test_client.post("/enrollments", json={"hostnameHint": "host-01"})

    assert second_response.status_code == 201
    assert second_response.json()["token"] != body["token"]
    assert body["token"] not in repr(app.state.xdr_store.enrollments)


def test_endpoint_event_ingestion_upserts_endpoint_metadata():
    test_client = client()
    headers = enrollment_headers(test_client)

    response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
            "hostname": "demo-endpoint-01",
            "ipAddresses": ["192.0.2.50"],
            "currentUser": "SOC-DEMO\\analyst",
            "health": "healthy",
            "attributes": {"os": "Linux"},
        },
    )

    assert response.status_code == 201
    endpoint = test_client.get("/endpoints/end_01").json()
    assert endpoint["id"] == "end_01"
    assert endpoint["hostname"] == "demo-endpoint-01"
    assert endpoint["ipAddresses"] == ["192.0.2.50"]
    assert endpoint["currentUser"] == "SOC-DEMO\\analyst"
    assert endpoint["lastSeenAt"] == "2026-05-08T12:00:00Z"
    assert endpoint["health"] == "healthy"
    assert "token" not in endpoint


def test_windows_security_endpoint_events_are_accepted_and_timeline_visible():
    test_client = client()
    headers = enrollment_headers(test_client)

    response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_win_dc01",
            "eventType": "auth.failed_login",
            "occurredAt": "2026-05-12T13:30:00Z",
            "hostname": "WIN-SOC-DC01",
            "ipAddresses": ["192.0.2.10"],
            "currentUser": "FORTIDASHBOARD\\felipe",
            "health": "warning",
            "attributes": {
                "source": "agent_private.windows_security",
                "windowsEventId": 4625,
                "count": 6,
                "sourceIp": "192.0.2.77",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["endpoint"]["id"] == "end_win_dc01"
    assert body["endpoint"]["health"] == "warning"
    assert body["timelineItem"]["eventType"] == "auth.failed_login"
    assert body["timelineItem"]["title"] == "Auth Failed Login"


def test_endpoint_timeline_is_newest_first():
    test_client = client()
    headers = enrollment_headers(test_client)
    for occurred_at, event_type in [
        ("2026-05-08T12:00:00Z", "heartbeat"),
        ("2026-05-08T12:01:00Z", "process.snapshot"),
        ("2026-05-08T12:02:00Z", "suspicious.process"),
    ]:
        response = test_client.post(
            "/endpoint-events",
            headers=headers,
            json={
                "endpointId": "end_01",
                "eventType": event_type,
                "occurredAt": occurred_at,
                "hostname": "demo-endpoint-01",
                "attributes": {"eventType": event_type},
            },
        )
        assert response.status_code == 201

    timeline = test_client.get("/endpoints/end_01/timeline").json()

    assert [item["eventType"] for item in timeline["items"]] == [
        "suspicious.process",
        "process.snapshot",
        "heartbeat",
    ]


def test_endpoint_events_require_valid_enrollment_token():
    test_client = client()

    missing_response = test_client.post(
        "/endpoint-events",
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
        },
    )
    invalid_response = test_client.post(
        "/endpoint-events",
        headers={"Authorization": "Bearer invalid-demo-token"},
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
        },
    )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401
    assert test_client.get("/endpoints/end_01").status_code == 404


def test_enrollment_token_cannot_report_for_a_different_endpoint_after_first_use():
    test_client = client()
    headers = enrollment_headers(test_client)

    first_response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
        },
    )
    spoof_response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_02",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:01:00Z",
        },
    )

    assert first_response.status_code == 201
    assert spoof_response.status_code == 403
    assert test_client.get("/endpoints/end_01").status_code == 200
    assert test_client.get("/endpoints/end_02").status_code == 404


def test_missing_endpoint_returns_404_for_detail_and_timeline():
    test_client = client()

    detail_response = test_client.get("/endpoints/missing")
    timeline_response = test_client.get("/endpoints/missing/timeline")

    assert detail_response.status_code == 404
    assert timeline_response.status_code == 404


def test_delete_endpoint_removes_inventory_and_timeline():
    test_client = client()
    headers = enrollment_headers(test_client)
    response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
            "hostname": "demo-endpoint-01",
        },
    )
    assert response.status_code == 201

    delete_response = test_client.delete("/endpoints/end_01")

    assert delete_response.status_code == 204
    assert test_client.get("/endpoints/end_01").status_code == 404
    assert test_client.get("/endpoints/end_01/timeline").status_code == 404
    assert test_client.get("/endpoints").json()["items"] == []


def test_endpoint_action_lifecycle_create_claim_and_complete():
    test_client = client()
    headers = enrollment_headers(test_client)
    heartbeat = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_win_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-19T12:00:00Z",
            "hostname": "WIN-LAB-01",
        },
    )
    assert heartbeat.status_code == 201

    created = test_client.post(
        "/endpoints/end_win_01/actions",
        json={"kind": "collect_now", "parameters": {"kind": "processes"}},
    )

    assert created.status_code == 201
    action = created.json()
    assert action["endpointId"] == "end_win_01"
    assert action["kind"] == "collect_now"
    assert action["status"] == "queued"

    claimed = test_client.post("/endpoints/end_win_01/actions/claim", headers=headers)

    assert claimed.status_code == 200
    assert claimed.json()["action"]["id"] == action["id"]
    assert claimed.json()["action"]["status"] == "claimed"

    completed = test_client.post(
        f"/endpoints/end_win_01/actions/{action['id']}/result",
        headers=headers,
        json={"status": "completed", "result": {"posted": ["process.snapshot"]}},
    )

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["result"] == {"posted": ["process.snapshot"]}


def test_endpoint_action_claim_requires_bound_enrollment_token():
    test_client = client()
    headers = enrollment_headers(test_client)
    other_headers = enrollment_headers(test_client)
    assert test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_win_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-19T12:00:00Z",
        },
    ).status_code == 201
    assert test_client.post(
        "/endpoint-events",
        headers=other_headers,
        json={
            "endpointId": "end_win_02",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-19T12:00:00Z",
        },
    ).status_code == 201
    assert test_client.post(
        "/endpoints/end_win_01/actions",
        json={"kind": "collect_now"},
    ).status_code == 201

    response = test_client.post("/endpoints/end_win_01/actions/claim", headers=other_headers)

    assert response.status_code == 403


def test_simulator_creates_deterministic_demo_endpoint_and_events(monkeypatch):
    test_client = client()

    disabled_response = test_client.post("/simulator/events")
    assert disabled_response.status_code == 404

    monkeypatch.setenv("XDR_RICO_ENABLE_SIMULATOR", "true")
    response = test_client.post("/simulator/events")

    assert response.status_code == 201
    body = response.json()
    assert body["endpoint"]["id"] == "demo-endpoint-01"
    assert body["createdEvents"] == 4
    endpoint = test_client.get("/endpoints/demo-endpoint-01").json()
    assert endpoint["hostname"] == "demo-endpoint-01"
    assert endpoint["health"] == "warning"
    timeline = test_client.get("/endpoints/demo-endpoint-01/timeline").json()
    assert [item["eventType"] for item in timeline["items"]] == [
        "suspicious.process",
        "connection.snapshot",
        "process.snapshot",
        "heartbeat",
    ]
    assert [item["attributes"]["source"] for item in timeline["items"]] == [
        "simulator",
        "simulator",
        "simulator",
        "simulator",
    ]


def test_endpoint_context_correlation_matches_ip_hostname_and_username():
    test_client = client()
    headers = enrollment_headers(test_client)
    for occurred_at, event_type in [
        ("2026-05-08T12:00:00Z", "heartbeat"),
        ("2026-05-08T12:01:00Z", "process.snapshot"),
    ]:
        response = test_client.post(
            "/endpoint-events",
            headers=headers,
            json={
                "endpointId": "end_01",
                "eventType": event_type,
                "occurredAt": occurred_at,
                "hostname": "demo-endpoint-01",
                "ipAddresses": ["192.0.2.50"],
                "currentUser": "SOC-DEMO\\analyst",
                "health": "warning",
                "attributes": {"source": "test"},
            },
        )
        assert response.status_code == 201

    response = test_client.post(
        "/correlations/endpoint-context",
        json={
            "entities": {
                "sourceIp": "192.0.2.50",
                "hostname": "demo-endpoint-01",
                "username": "analyst",
            },
            "limit": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    match = body["items"][0]
    assert match["endpoint"]["id"] == "end_01"
    assert match["score"] > 0
    assert {field["field"] for field in match["matchedFields"]} == {
        "sourceIp",
        "hostname",
        "username",
    }
    assert [item["eventType"] for item in match["timeline"]] == [
        "process.snapshot",
        "heartbeat",
    ]


def test_endpoint_context_correlation_returns_empty_for_unmatched_entities():
    test_client = client()
    headers = enrollment_headers(test_client)
    response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_01",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
            "hostname": "demo-endpoint-01",
            "ipAddresses": ["192.0.2.50"],
            "currentUser": "SOC-DEMO\\analyst",
        },
    )
    assert response.status_code == 201

    response = test_client.post(
        "/correlations/endpoint-context",
        json={
            "entities": {
                "sourceIp": "203.0.113.10",
                "hostname": "other-endpoint",
                "username": "other-user",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "incidentEntities": {
            "sourceIp": "203.0.113.10",
            "hostname": "other-endpoint",
            "username": "other-user",
        },
        "items": [],
        "total": 0,
    }


def test_enrollment_token_survives_legacy_memory_clear():
    test_client = client()
    headers = enrollment_headers(test_client)

    clear_legacy_memory_maps()
    response = test_client.post(
        "/endpoint-events",
        headers=headers,
        json={
            "endpointId": "end_persisted_auth",
            "eventType": "heartbeat",
            "occurredAt": "2026-05-08T12:00:00Z",
            "hostname": "persisted-auth-host",
        },
    )

    assert response.status_code == 201
    assert response.json()["endpoint"]["id"] == "end_persisted_auth"


def test_endpoint_and_timeline_survive_legacy_memory_clear():
    test_client = client()
    headers = enrollment_headers(test_client)
    for occurred_at, event_type in [
        ("2026-05-08T12:00:00Z", "heartbeat"),
        ("2026-05-08T12:02:00Z", "suspicious.process"),
    ]:
        response = test_client.post(
            "/endpoint-events",
            headers=headers,
            json={
                "endpointId": "end_persisted",
                "eventType": event_type,
                "occurredAt": occurred_at,
                "hostname": "persisted-host",
                "ipAddresses": ["192.0.2.77"],
                "currentUser": "SOC-DEMO\\analyst",
                "health": "warning",
                "attributes": {"source": "persistence-test"},
            },
        )
        assert response.status_code == 201

    clear_legacy_memory_maps()
    endpoint = test_client.get("/endpoints/end_persisted")
    timeline = test_client.get("/endpoints/end_persisted/timeline")

    assert endpoint.status_code == 200
    assert endpoint.json()["hostname"] == "persisted-host"
    assert endpoint.json()["ipAddresses"] == ["192.0.2.77"]
    assert timeline.status_code == 200
    assert [item["eventType"] for item in timeline.json()["items"]] == [
        "suspicious.process",
        "heartbeat",
    ]
