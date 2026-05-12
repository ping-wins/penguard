import json
from datetime import UTC, datetime

from agent_private import cli
from agent_private.cli import (
    build_connection_snapshot_payload,
    build_heartbeat_payload,
    build_identity_payload,
    build_process_snapshot_payload,
    main,
)


def test_build_identity_payload_has_required_fields():
    payload = build_identity_payload(
        hostname="demo-endpoint-01",
        username="SOC-DEMO\\analyst",
    )

    assert payload["hostname"] == "demo-endpoint-01"
    assert payload["username"] == "SOC-DEMO\\analyst"
    assert payload["service"] == "agent_private"


def test_build_heartbeat_payload_uses_identity_and_endpoint_id():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    identity = {
        "service": "agent_private",
        "hostname": "demo-endpoint-01",
        "username": "analyst",
        "os": "Linux",
    }

    payload = build_heartbeat_payload(
        endpoint_id="end_01",
        identity=identity,
        ip_addresses=["192.0.2.50"],
        occurred_at=occurred_at,
    )

    assert payload == {
        "endpointId": "end_01",
        "eventType": "heartbeat",
        "occurredAt": "2026-05-08T12:00:00.000Z",
        "hostname": "demo-endpoint-01",
        "ipAddresses": ["192.0.2.50"],
        "currentUser": "analyst",
        "attributes": {
            "service": "agent_private",
            "username": "analyst",
            "os": "Linux",
        },
    }


def test_build_process_snapshot_payload_normalizes_process_iter_rows():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    processes = [
        {
            "pid": 1200,
            "name": "powershell.exe",
            "username": "SOC-DEMO\\analyst",
            "status": "running",
            "cpu_percent": 3.2,
            "memory_info": type("Memory", (), {"rss": 123456})(),
        }
    ]

    payload = build_process_snapshot_payload(
        endpoint_id="end_01",
        hostname="demo-endpoint-01",
        ip_addresses=["192.0.2.50"],
        processes=processes,
        occurred_at=occurred_at,
    )

    assert payload["eventType"] == "process.snapshot"
    assert payload["attributes"]["processes"] == [
        {
            "pid": 1200,
            "name": "powershell.exe",
            "username": "SOC-DEMO\\analyst",
            "status": "running",
            "cpuPercent": 3.2,
            "memoryRssBytes": 123456,
        }
    ]


def test_build_process_snapshot_payload_preserves_pre_normalized_rows():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    processes = [
        {
            "pid": 1200,
            "name": "python",
            "username": "analyst",
            "status": "running",
            "cpuPercent": 3.2,
            "memoryRssBytes": 123456,
        }
    ]

    payload = build_process_snapshot_payload(
        endpoint_id="end_01",
        hostname="demo-endpoint-01",
        ip_addresses=["192.0.2.50"],
        processes=processes,
        occurred_at=occurred_at,
    )

    assert payload["attributes"]["processes"][0]["cpuPercent"] == 3.2
    assert payload["attributes"]["processes"][0]["memoryRssBytes"] == 123456


def test_build_connection_snapshot_payload_normalizes_connection_rows():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    connections = [
        type(
            "Connection",
            (),
            {
                "fd": 7,
                "family": 2,
                "type": 1,
                "laddr": ("192.0.2.50", 54122),
                "raddr": ("198.51.100.20", 443),
                "status": "ESTABLISHED",
                "pid": 1200,
            },
        )()
    ]

    payload = build_connection_snapshot_payload(
        endpoint_id="end_01",
        hostname="demo-endpoint-01",
        ip_addresses=["192.0.2.50"],
        connections=connections,
        occurred_at=occurred_at,
    )

    assert payload["eventType"] == "connection.snapshot"
    assert payload["attributes"]["connections"] == [
        {
            "fd": 7,
            "family": "AF_INET",
            "type": "SOCK_STREAM",
            "localAddress": {"ip": "192.0.2.50", "port": 54122},
            "remoteAddress": {"ip": "198.51.100.20", "port": 443},
            "status": "ESTABLISHED",
            "pid": 1200,
        }
    ]


def test_heartbeat_dry_run_prints_json_without_posting(monkeypatch, capsys):
    posted = False

    def fail_if_posted(*args, **kwargs):
        nonlocal posted
        posted = True
        raise AssertionError("dry-run should not post")

    monkeypatch.setattr(cli, "post_endpoint_event", fail_if_posted)
    monkeypatch.setattr(cli, "get_ip_addresses", lambda: ["192.0.2.50"])
    monkeypatch.setattr(
        cli,
        "build_identity_payload",
        lambda: {
            "service": "agent_private",
            "hostname": "demo-endpoint-01",
            "username": "analyst",
            "os": "Linux",
        },
    )

    main(["heartbeat", "--endpoint-id", "end_01"])

    output = json.loads(capsys.readouterr().out)
    assert output["eventType"] == "heartbeat"
    assert output["endpointId"] == "end_01"
    assert posted is False


def test_post_endpoint_event_uses_bff_endpoint_and_bearer_header(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(cli.httpx, "post", fake_post)

    cli.post_endpoint_event(
        api_url="http://localhost:8000",
        enrollment_token="demo-token",
        payload={"endpointId": "end_01"},
        timeout=1.0,
    )

    assert calls == [
        {
            "url": "http://localhost:8000/api/weapons/endpoint-events",
            "headers": {"Authorization": "Bearer demo-token"},
            "json": {"endpointId": "end_01"},
            "timeout": 1.0,
        }
    ]


def test_simulate_prints_deterministic_events(capsys):
    main(["simulate", "--endpoint-id", "end_01"])

    output = json.loads(capsys.readouterr().out)
    assert [event["eventType"] for event in output] == [
        "heartbeat",
        "process.snapshot",
        "connection.snapshot",
    ]
    assert {event["occurredAt"] for event in output} == {"2026-05-08T12:00:00.000Z"}


def test_default_command_launches_tui(monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "run_tui", lambda: calls.append("tui"))

    main([])

    assert calls == ["tui"]


def test_tui_command_launches_tui(monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "run_tui", lambda: calls.append("tui"))

    main(["tui"])

    assert calls == ["tui"]
