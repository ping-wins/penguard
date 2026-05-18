from fastapi.testclient import TestClient

from app import main
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


def _clear_legacy_memory_lists() -> None:
    for attr in ("events", "incidents"):
        value = getattr(main, attr, None)
        if isinstance(value, list):
            value.clear()


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
    login = client.post("/events", json=_event_payload("auth.failed_login", count=3)).json()
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
        incident["title"] == "Possible authentication brute force"
        and login["id"] in incident["eventIds"]
        for incident in incidents
    )
    assert any(
        incident["title"] == "Suspicious endpoint connection"
        and suspicious["id"] in incident["eventIds"]
        and incident["severity"] == "high"
        for incident in incidents
    )
    assert not any(below_threshold["id"] in incident["eventIds"] for incident in incidents)


def test_failed_login_requires_three_attempts_for_bruteforce_incident():
    below_threshold = client.post(
        "/events",
        json=_event_payload("auth.failed_login", count=2, source_ip="198.51.100.21"),
    ).json()
    threshold = client.post(
        "/events",
        json=_event_payload("auth.failed_login", count=3, source_ip="198.51.100.22"),
    ).json()

    incidents = client.get("/incidents").json()

    assert not any(below_threshold["id"] in incident["eventIds"] for incident in incidents)
    brute_force_incidents = [
        incident
        for incident in incidents
        if incident["ruleId"] == "repeated_failed_login" and threshold["id"] in incident["eventIds"]
    ]
    assert brute_force_incidents
    assert brute_force_incidents[0]["attributes"]["detection"]["thresholds"] == [
        {"path": "attributes.count", "operator": "gte", "value": 3}
    ]


def test_failed_login_burst_aggregates_three_individual_attempts_for_same_subject():
    client.post("/admin/reset")
    payload = _event_payload("auth.failed_login", count=1, source_ip="203.0.113.45")
    payload["entities"] = {
        "sourceIp": "203.0.113.45",
        "user": "admin",
        "integrationId": "int_fgt_live",
    }

    first = client.post(
        "/events",
        json={**payload, "occurredAt": "2026-05-14T22:00:00.000Z"},
    ).json()
    second = client.post(
        "/events",
        json={**payload, "occurredAt": "2026-05-14T22:00:20.000Z"},
    ).json()
    third = client.post(
        "/events",
        json={**payload, "occurredAt": "2026-05-14T22:00:40.000Z"},
    ).json()

    incidents = client.get("/incidents").json()

    assert not any(first["id"] in incident["eventIds"] for incident in incidents)
    assert not any(second["id"] in incident["eventIds"] for incident in incidents)
    brute_force = next(
        incident for incident in incidents
        if incident["ruleId"] == "repeated_failed_login" and third["id"] in incident["eventIds"]
    )
    assert brute_force["severity"] == "high"
    assert brute_force["attributes"]["attackType"] == "brute_force"
    assert brute_force["attributes"]["count"] == 3
    assert brute_force["attributes"]["detection"]["observedCount"] == 3


def test_allowed_fortigate_traffic_burst_creates_port_scan_incident():
    client.post("/admin/reset")

    for port in range(2200, 2220):
        payload = _event_payload(
            "network.event",
            severity="info",
            source_ip="192.0.2.50",
        )
        payload["entities"] = {
            "integrationId": "integration-lab",
            "sourceIp": "192.0.2.50",
            "destinationIp": "198.51.100.10",
        }
        payload["attributes"] = {
            "integrationId": "integration-lab",
            "sourceIp": "192.0.2.50",
            "destinationIp": "198.51.100.10",
            "destinationPort": port,
            "service": f"tcp/{port}",
            "action": "accept",
            "policyId": "FD_LAB_ALLOW_SCAN",
            "subtype": "forward",
            "logid": f"000000{port}",
        }
        response = client.post("/events", json=payload)
        assert response.status_code == 200

    incidents = client.get("/incidents").json()
    matching = [
        incident
        for incident in incidents
        if incident["ruleId"] == "network_scan"
        and incident["attributes"].get("sourceIp") == "192.0.2.50"
        and incident["attributes"].get("destinationIp") == "198.51.100.10"
    ]

    assert len(matching) == 1
    incident = matching[0]
    assert incident["severity"] == "high"
    assert incident["attributes"]["attackType"] == "allowed_port_scan"
    assert incident["attributes"]["uniqueDestinationPortCount"] == 20
    assert incident["attributes"]["scanWindowSeconds"] == 60
    assert 2200 in incident["attributes"]["destinationPorts"]
    assert 2219 in incident["attributes"]["destinationPorts"]


def test_fortigate_timeout_traffic_burst_creates_allowed_port_scan_incident():
    client.post("/admin/reset")

    for port in range(120, 140):
        payload = _event_payload(
            "network.event",
            severity="medium",
            source_ip="192.0.2.60",
        )
        payload["entities"] = {
            "integrationId": "int_fgt_lab",
            "sourceIp": "192.0.2.60",
            "destinationIp": "198.51.100.60",
        }
        payload["attributes"] = {
            "integrationId": "int_fgt_lab",
            "sourceIp": "192.0.2.60",
            "destinationIp": "198.51.100.60",
            "destinationPort": port,
            "service": f"tcp/{port}",
            "action": "timeout",
            "policyId": "1",
            "policyName": "FD_LAB_ALLOW_32FD0707AD9A",
            "subtype": "forward",
        }
        response = client.post("/events", json=payload)
        assert response.status_code == 200

    incidents = client.get("/incidents").json()
    matching = [
        incident
        for incident in incidents
        if incident["ruleId"] == "network_scan"
        and incident["attributes"].get("sourceIp") == "192.0.2.60"
        and incident["attributes"].get("destinationIp") == "198.51.100.60"
    ]

    assert len(matching) == 1
    assert matching[0]["attributes"]["attackType"] == "allowed_port_scan"
    assert matching[0]["attributes"]["uniqueDestinationPortCount"] == 20


def test_fortigate_http_flow_burst_creates_waf_dos_incident():
    client.post("/admin/reset")

    event = None
    for _index in range(100):
        payload = _event_payload(
            "network.event",
            severity="medium",
            source_ip="10.10.10.10",
        )
        payload["occurredAt"] = "2026-05-17T20:24:30.000Z"
        payload["entities"] = {
            "integrationId": "int_fgt_lab",
            "sourceIp": "10.10.10.10",
            "destinationIp": "10.10.20.30",
        }
        payload["attributes"] = {
            "integrationId": "int_fgt_lab",
            "sourceIp": "10.10.10.10",
            "destinationIp": "10.10.20.30",
            "destinationPort": 80,
            "service": "HTTP",
            "action": "close",
            "policyId": "2",
            "subtype": "forward",
        }
        response = client.post("/events/ingest", json=payload)
        assert response.status_code == 200
        event = response.json()["event"]

    assert event is not None
    assert event["eventType"] == "waf.dos"
    assert event["severity"] == "critical"
    assert event["attributes"]["attackType"] == "http_flood"
    assert event["attributes"]["count"] == 100
    assert event["attributes"]["ingestionMode"] == "fortigate_flow_inference"

    incidents = client.get("/incidents").json()
    matching = [
        incident
        for incident in incidents
        if incident["ruleId"] == "fortiweb_dos_activity"
        and incident["attributes"].get("sourceIp") == "10.10.10.10"
        and incident["attributes"].get("destinationIp") == "10.10.20.30"
    ]

    assert len(matching) == 1
    assert matching[0]["severity"] == "critical"
    assert matching[0]["triageLevel"] == "T1"
    assert matching[0]["attributes"]["attackType"] == "http_flood"
    assert matching[0]["attributes"]["ingestionMode"] == "fortigate_flow_inference"

    suppressed = client.post("/events/ingest", json=payload).json()["event"]
    assert suppressed["eventType"] == "network.event"
    incidents_after_suppression = client.get("/incidents").json()
    assert len(
        [
            incident
            for incident in incidents_after_suppression
            if incident["ruleId"] == "fortiweb_dos_activity"
        ]
    ) == 1

    payload["occurredAt"] = "2026-05-17T20:35:30.000Z"
    for _index in range(100):
        response = client.post("/events/ingest", json=payload)
        assert response.status_code == 200

    incidents_after_second_burst = client.get("/incidents").json()
    matching_after_second_burst = [
        incident
        for incident in incidents_after_second_burst
        if incident["ruleId"] == "fortiweb_dos_activity"
        and incident["attributes"].get("sourceIp") == "10.10.10.10"
        and incident["attributes"].get("destinationIp") == "10.10.20.30"
    ]
    assert len(matching_after_second_burst) == 1


def test_incidents_preserve_event_provenance_for_demo_badges():
    event = client.post(
        "/events",
        json={
            "source": "demo.replay",
            "eventType": "network.deny",
            "severity": "high",
            "occurredAt": "2026-05-12T12:00:00.000Z",
            "entities": {"sourceIp": "203.0.113.77"},
            "attributes": {
                "count": 42,
                "demoRunId": "demo_contract_01",
                "attackType": "port_scan",
            },
        },
    ).json()

    incident = next(
        incident
        for incident in client.get("/incidents").json()
        if event["id"] in incident["eventIds"]
    )

    assert incident["source"] == "kowalski"
    assert incident["origin"] == {"kind": "demo.replay"}
    assert incident["attributes"]["source"] == "demo.replay"
    assert incident["attributes"]["demoRunId"] == "demo_contract_01"
    assert incident["attributes"]["attackType"] == "port_scan"


def test_incidents_include_detection_explanation_for_analysts():
    event = client.post(
        "/events",
        json={
            "source": "demo.replay",
            "eventType": "network.deny",
            "severity": "high",
            "occurredAt": "2026-05-12T12:00:00.000Z",
            "entities": {"sourceIp": "203.0.113.77", "destinationIp": "192.168.0.50"},
            "attributes": {
                "count": 42,
                "demoRunId": "demo_contract_02",
                "attackType": "port_scan",
            },
        },
    ).json()

    incident = next(
        incident
        for incident in client.get("/incidents").json()
        if event["id"] in incident["eventIds"]
    )

    assert incident["attributes"]["detection"] == {
        "ruleId": "denied_traffic_burst",
        "title": "Denied traffic burst",
        "summary": "Denied network traffic exceeded the configured burst threshold.",
        "matchedEventType": "network.deny",
        "observedCount": 42,
        "thresholds": [{"path": "attributes.count", "operator": "gte", "value": 20}],
    }


def test_lists_detection_rules_with_safe_condition_metadata():
    response = client.get("/rules")

    assert response.status_code == 200
    rules = response.json()
    rule_ids = {rule["id"] for rule in rules}
    assert rule_ids >= {
        "network_scan",
        "denied_traffic_burst",
        "repeated_failed_login",
        "suspicious_endpoint_connection",
        "fortigate_resource_pressure",
    }
    resource_rule = next(rule for rule in rules if rule["id"] == "fortigate_resource_pressure")
    assert resource_rule["match"] == "any"
    assert {condition["operator"] for condition in resource_rule["conditions"]} == {"gte"}
    assert {condition["path"] for condition in resource_rule["conditions"]} == {
        "attributes.cpuPercent",
        "attributes.memoryPercent",
    }


def test_windows_ad_detection_rules_create_identity_and_file_incidents():
    failed_login = client.post(
        "/events",
        json={
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
            },
        },
    ).json()
    privileged = client.post(
        "/events",
        json={
            "source": "xdr_rico.agent_private",
            "eventType": "auth.privileged_logon",
            "severity": "high",
            "occurredAt": "2026-05-12T13:31:00.000Z",
            "entities": {
                "endpointId": "end_win_file01",
                "hostname": "WIN-SOC-FILE01",
                "username": "FORTIDASHBOARD\\administrator",
            },
            "attributes": {
                "source": "agent_private.windows_security",
                "windowsEventId": 4672,
                "privileged": True,
                "unusualHost": True,
            },
        },
    ).json()
    file_change = client.post(
        "/events",
        json={
            "source": "xdr_rico.agent_private",
            "eventType": "file.change",
            "severity": "high",
            "occurredAt": "2026-05-12T13:32:00.000Z",
            "entities": {
                "endpointId": "end_win_file01",
                "hostname": "WIN-SOC-FILE01",
                "username": "FORTIDASHBOARD\\svc-backup",
                "filePath": r"C:\Sensitive\payroll.xlsx",
            },
            "attributes": {
                "source": "agent_private.windows_security",
                "windowsEventId": 4663,
                "criticalPath": True,
            },
        },
    ).json()

    incidents = client.get("/incidents").json()

    assert any(
        incident["ruleId"] == "repeated_failed_login"
        and failed_login["id"] in incident["eventIds"]
        for incident in incidents
    )
    assert any(
        incident["ruleId"] == "privileged_logon_unusual_host"
        and privileged["id"] in incident["eventIds"]
        and incident["triageLevel"] == "T1"
        for incident in incidents
    )
    assert any(
        incident["ruleId"] == "critical_server_file_change"
        and file_change["id"] in incident["eventIds"]
        and incident["triageLevel"] == "T1"
        for incident in incidents
    )


def test_high_cpu_or_memory_telemetry_creates_resource_pressure_incident():
    cpu_event = client.post(
        "/events",
        json={
            "source": "fortigate",
            "eventType": "fortigate.system_status",
            "severity": "medium",
            "occurredAt": "2026-05-08T12:00:00.000Z",
            "entities": {"integrationId": "int_fgt_01", "hostname": "fortigate-lab"},
            "attributes": {"cpuPercent": 91, "memoryPercent": 42},
        },
    ).json()
    memory_event = client.post(
        "/events",
        json={
            "source": "fortigate",
            "eventType": "fortigate.system_status",
            "severity": "medium",
            "occurredAt": "2026-05-08T12:01:00.000Z",
            "entities": {"integrationId": "int_fgt_01", "hostname": "fortigate-lab"},
            "attributes": {"cpuPercent": 15, "memoryPercent": 94},
        },
    ).json()

    incidents = client.get("/incidents", params={"severity": "high"}).json()

    resource_incidents = [
        incident for incident in incidents if incident["title"] == "FortiGate resource pressure"
    ]
    assert {event_id for incident in resource_incidents for event_id in incident["eventIds"]} >= {
        cpu_event["id"],
        memory_event["id"],
    }
    assert {incident["ruleId"] for incident in resource_incidents} == {
        "fortigate_resource_pressure"
    }


def test_gte_conditions_reject_non_numeric_values_without_evaluating_strings():
    event = client.post(
        "/events",
        json={
            "source": "fortigate",
            "eventType": "fortigate.system_status",
            "severity": "medium",
            "occurredAt": "2026-05-08T12:00:00.000Z",
            "entities": {"integrationId": "int_fgt_01"},
            "attributes": {
                "cpuPercent": "__import__('os').system('id')",
                "memoryPercent": "not-a-number",
            },
        },
    ).json()

    incidents = client.get("/incidents").json()

    assert not any(event["id"] in incident["eventIds"] for incident in incidents)


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


def test_events_and_incidents_survive_legacy_memory_clear():
    event = client.post(
        "/events",
        json=_event_payload("network.scan", source_ip="192.0.2.201"),
    ).json()

    _clear_legacy_memory_lists()

    events = client.get("/events", params={"eventType": "network.scan"}).json()
    incidents = client.get("/incidents", params={"severity": "high"}).json()

    assert any(item["id"] == event["id"] for item in events)
    assert any(
        incident["title"] == "Possible port scan" and event["id"] in incident["eventIds"]
        for incident in incidents
    )


def test_incident_status_update_survives_legacy_memory_clear():
    event = client.post(
        "/events",
        json=_event_payload("network.scan", source_ip="192.0.2.202"),
    ).json()
    incident = next(
        incident
        for incident in client.get("/incidents").json()
        if event["id"] in incident["eventIds"]
    )

    response = client.patch(f"/incidents/{incident['id']}", json={"status": "triaged"})
    _clear_legacy_memory_lists()
    detail = client.get(f"/incidents/{incident['id']}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["status"] == "triaged"
    assert detail.json()["timeline"][-1]["status"] == "triaged"


def test_waf_attack_creates_incident():
    client.post("/admin/reset")
    response = client.post(
        "/events/ingest",
        json={
            "eventType": "waf.attack",
            "source": "fortiweb",
            "severity": "high",
            "message": "SQL Injection Detected",
            "occurredAt": "2026-05-15T12:00:00Z",
            "entities": {
                "sourceIp": "203.0.113.50",
                "destinationIp": "198.51.100.10",
                "httpHost": "landing.example.test",
                "integrationId": "int_fweb_landing",
            },
            "attributes": {
                "action": "block",
                "policy": "landing-waf-policy",
                "method": "GET",
                "url": "/demo/search?q=' OR 1=1--",
                "count": 1,
            },
        },
    )

    assert response.status_code == 200
    incident = response.json()["incident"]
    assert incident["title"] == "FortiWeb WAF attack blocked"
    assert incident["severity"] == "high"
    assert incident["triageLevel"] == "T1"
    assert incident["entities"]["sourceIp"] == "203.0.113.50"
    assert incident["entities"]["httpHost"] == "landing.example.test"
    assert incident["attributes"]["policy"] == "landing-waf-policy"


def test_waf_dos_creates_critical_incident():
    client.post("/admin/reset")
    response = client.post(
        "/events/ingest",
        json={
            "eventType": "waf.dos",
            "source": "fortiweb",
            "severity": "critical",
            "message": "HTTP Flood detected",
            "occurredAt": "2026-05-15T12:00:00Z",
            "entities": {
                "sourceIp": "203.0.113.60",
                "httpHost": "landing.example.test",
            },
            "attributes": {
                "action": "block",
                "count": 250,
            },
        },
    )

    assert response.status_code == 200
    incident = response.json()["incident"]
    assert incident["title"] == "FortiWeb DoS activity detected"
    assert incident["severity"] == "critical"
    assert incident["triageLevel"] == "T1"
