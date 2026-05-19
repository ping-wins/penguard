import json
from datetime import UTC, datetime

import agent_private.tui as tui
from agent_private import cli, runner
from agent_private.cli import (
    build_connection_snapshot_payload,
    build_heartbeat_payload,
    build_identity_payload,
    build_process_snapshot_payload,
    build_sysmon_event_payloads,
    build_windows_security_event_payloads,
    main,
    parse_sysmon_events,
    parse_windows_security_events,
)


def test_build_identity_payload_has_required_fields():
    payload = build_identity_payload(
        hostname="demo-endpoint-01",
        username="SOC-DEMO\\analyst",
    )

    assert payload["hostname"] == "demo-endpoint-01"
    assert payload["username"] == "SOC-DEMO\\analyst"
    assert payload["service"] == "agent_private"


def test_pair_discovers_dashboard_posts_token_and_saves_config(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(tui, "default_config_path", lambda: config_path)
    monkeypatch.setattr(
        cli,
        "discover_dashboard",
        lambda **_kwargs: type("Discovery", (), {"api_url": "http://192.168.56.1:8000"})(),
    )
    monkeypatch.setattr(
        cli,
        "_identity_context",
        lambda: (
            {
                "service": "agent_private",
                "hostname": "WIN-LAB-01",
                "username": "Administrator",
                "os": "Windows",
            },
            ["192.168.56.101"],
        ),
    )

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"endpointId": "enr_01"}

    def post(url, *, json, timeout):
        assert url == "http://192.168.56.1:8000/api/weapons/agent/pair"
        assert json["enrollmentToken"] == "secret-enrollment-token"
        assert json["hostname"] == "WIN-LAB-01"
        assert json["ipAddresses"] == ["192.168.56.101"]
        assert timeout == cli.DEFAULT_TIMEOUT_SECONDS
        return Response()

    monkeypatch.setattr(cli.httpx, "post", post)

    main(["pair", "secret-enrollment-token"])

    output = capsys.readouterr().out
    assert "secret-enrollment-token" not in output
    stored = tui.load_config(config_path)
    assert stored.api_url == "http://192.168.56.1:8000"
    assert stored.endpoint_id == "enr_01"
    assert stored.enrollment_token == "secret-enrollment-token"


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


def test_build_connection_snapshot_payload_preserves_collected_connection_dicts():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    connections = [
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

    payload = build_connection_snapshot_payload(
        endpoint_id="end_01",
        hostname="demo-endpoint-01",
        ip_addresses=["192.0.2.50"],
        connections=connections,
        occurred_at=occurred_at,
    )

    assert payload["eventType"] == "connection.snapshot"
    assert payload["attributes"]["connections"] == connections


def test_connection_snapshot_marks_high_risk_remote_port_as_suspicious():
    occurred_at = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)

    payload = build_connection_snapshot_payload(
        endpoint_id="end_01",
        hostname="demo-endpoint-01",
        ip_addresses=["192.0.2.50"],
        connections=[
            {
                "fd": 7,
                "family": "AF_INET",
                "type": "SOCK_STREAM",
                "localAddress": {"ip": "192.0.2.50", "port": 54122},
                "remoteAddress": {"ip": "10.10.10.10", "port": 4444},
                "status": "ESTABLISHED",
                "pid": 1200,
            }
        ],
        occurred_at=occurred_at,
    )

    connection = payload["attributes"]["connections"][0]
    assert connection["suspicious"] is True
    assert connection["remoteIp"] == "10.10.10.10"
    assert connection["remotePort"] == 4444
    assert "high-risk remote port 4444" in connection["suspiciousReason"]


def test_parse_windows_security_events_extracts_event_data_from_wevtutil_xml():
    raw_xml = """
    <Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
      <System>
        <Provider Name="Microsoft-Windows-Security-Auditing" />
        <EventID>4625</EventID>
        <TimeCreated SystemTime="2026-05-12T13:30:00.0000000Z" />
        <Computer>WIN-SOC-DC01.fortidashboard.local</Computer>
        <EventRecordID>1001</EventRecordID>
      </System>
      <EventData>
        <Data Name="TargetUserName">felipe</Data>
        <Data Name="TargetDomainName">FORTIDASHBOARD</Data>
        <Data Name="IpAddress">192.0.2.77</Data>
        <Data Name="LogonType">3</Data>
        <Data Name="Status">0xc000006d</Data>
      </EventData>
    </Event>
    """

    events = parse_windows_security_events(raw_xml)

    assert events == [
        {
            "eventId": 4625,
            "occurredAt": "2026-05-12T13:30:00.000Z",
            "computer": "WIN-SOC-DC01.fortidashboard.local",
            "recordId": "1001",
            "data": {
                "TargetUserName": "felipe",
                "TargetDomainName": "FORTIDASHBOARD",
                "IpAddress": "192.0.2.77",
                "LogonType": "3",
                "Status": "0xc000006d",
            },
        }
    ]


def test_build_windows_security_event_payloads_aggregates_failed_logons():
    events = [
        {
            "eventId": 4625,
            "occurredAt": "2026-05-12T13:30:00.000Z",
            "computer": "WIN-SOC-DC01",
            "recordId": str(index),
            "data": {
                "TargetUserName": "felipe",
                "TargetDomainName": "FORTIDASHBOARD",
                "IpAddress": "192.0.2.77",
            },
        }
        for index in range(1, 7)
    ]

    payloads = build_windows_security_event_payloads(
        endpoint_id="end_win_dc01",
        hostname="WIN-SOC-DC01",
        ip_addresses=["192.0.2.10"],
        events=events,
    )

    assert payloads == [
        {
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
                "username": "FORTIDASHBOARD\\felipe",
                "sourceIp": "192.0.2.77",
                "recordIds": ["1", "2", "3", "4", "5", "6"],
            },
        }
    ]


def test_build_windows_security_event_payloads_marks_privileged_and_critical_events():
    events = [
        {
            "eventId": 4672,
            "occurredAt": "2026-05-12T13:31:00.000Z",
            "computer": "WIN-SOC-FILE01",
            "recordId": "2001",
            "data": {
                "SubjectUserName": "administrator",
                "SubjectDomainName": "FORTIDASHBOARD",
                "PrivilegeList": "SeBackupPrivilege SeDebugPrivilege",
            },
        },
        {
            "eventId": 4663,
            "occurredAt": "2026-05-12T13:32:00.000Z",
            "computer": "WIN-SOC-FILE01",
            "recordId": "2002",
            "data": {
                "SubjectUserName": "svc-backup",
                "SubjectDomainName": "FORTIDASHBOARD",
                "ObjectName": r"C:\Sensitive\payroll.xlsx",
                "Accesses": "WriteData",
            },
        },
    ]

    payloads = build_windows_security_event_payloads(
        endpoint_id="end_win_file01",
        hostname="WIN-SOC-FILE01",
        ip_addresses=["192.0.2.20"],
        events=events,
        allowed_admin_hosts=["WIN-SOC-DC01"],
        critical_paths=[r"C:\Sensitive"],
    )

    assert [payload["eventType"] for payload in payloads] == [
        "auth.privileged_logon",
        "file.change",
    ]
    assert payloads[0]["attributes"]["privileged"] is True
    assert payloads[0]["attributes"]["unusualHost"] is True
    assert payloads[1]["attributes"]["criticalPath"] is True
    assert payloads[1]["attributes"]["objectName"] == r"C:\Sensitive\payroll.xlsx"


def test_parse_sysmon_events_extracts_network_and_dns_records_from_wevtutil_xml():
    raw_xml = """
    <Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
      <System>
        <Provider Name="Microsoft-Windows-Sysmon" />
        <EventID>3</EventID>
        <TimeCreated SystemTime="2026-05-19T12:10:00.0000000Z" />
        <Computer>WIN-SOC-01.fortidashboard.local</Computer>
        <EventRecordID>3001</EventRecordID>
      </System>
      <EventData>
        <Data Name="RuleName">NetworkConnect</Data>
        <Data Name="UtcTime">2026-05-19 12:10:00.000</Data>
        <Data Name="ProcessGuid">{11111111-1111-1111-1111-111111111111}</Data>
        <Data Name="ProcessId">1200</Data>
        <Data Name="Image">C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe</Data>
        <Data Name="User">FORTIDASHBOARD\\analyst</Data>
        <Data Name="Protocol">tcp</Data>
        <Data Name="SourceIp">192.0.2.50</Data>
        <Data Name="SourcePort">54122</Data>
        <Data Name="DestinationIp">198.51.100.20</Data>
        <Data Name="DestinationHostname">suspicious.example</Data>
        <Data Name="DestinationPort">443</Data>
      </EventData>
    </Event>
    <Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
      <System>
        <Provider Name="Microsoft-Windows-Sysmon" />
        <EventID>22</EventID>
        <TimeCreated SystemTime="2026-05-19T12:10:01.0000000Z" />
        <Computer>WIN-SOC-01.fortidashboard.local</Computer>
        <EventRecordID>3002</EventRecordID>
      </System>
      <EventData>
        <Data Name="RuleName">DnsQuery</Data>
        <Data Name="UtcTime">2026-05-19 12:10:01.000</Data>
        <Data Name="ProcessGuid">{11111111-1111-1111-1111-111111111111}</Data>
        <Data Name="ProcessId">1200</Data>
        <Data Name="QueryName">suspicious.example</Data>
        <Data Name="QueryStatus">0</Data>
        <Data Name="QueryResults">198.51.100.20;</Data>
        <Data Name="Image">C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe</Data>
        <Data Name="User">FORTIDASHBOARD\\analyst</Data>
      </EventData>
    </Event>
    """

    events = parse_sysmon_events(raw_xml)

    assert events == [
        {
            "eventId": 3,
            "occurredAt": "2026-05-19T12:10:00.000Z",
            "computer": "WIN-SOC-01.fortidashboard.local",
            "recordId": "3001",
            "data": {
                "RuleName": "NetworkConnect",
                "UtcTime": "2026-05-19 12:10:00.000",
                "ProcessGuid": "{11111111-1111-1111-1111-111111111111}",
                "ProcessId": "1200",
                "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "User": r"FORTIDASHBOARD\analyst",
                "Protocol": "tcp",
                "SourceIp": "192.0.2.50",
                "SourcePort": "54122",
                "DestinationIp": "198.51.100.20",
                "DestinationHostname": "suspicious.example",
                "DestinationPort": "443",
            },
        },
        {
            "eventId": 22,
            "occurredAt": "2026-05-19T12:10:01.000Z",
            "computer": "WIN-SOC-01.fortidashboard.local",
            "recordId": "3002",
            "data": {
                "RuleName": "DnsQuery",
                "UtcTime": "2026-05-19 12:10:01.000",
                "ProcessGuid": "{11111111-1111-1111-1111-111111111111}",
                "ProcessId": "1200",
                "QueryName": "suspicious.example",
                "QueryStatus": "0",
                "QueryResults": "198.51.100.20;",
                "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "User": r"FORTIDASHBOARD\analyst",
            },
        },
    ]


def test_build_sysmon_event_payloads_normalizes_network_and_dns_events():
    payloads = build_sysmon_event_payloads(
        endpoint_id="end_win_01",
        hostname="WIN-SOC-01",
        ip_addresses=["192.0.2.50"],
        events=[
            {
                "eventId": 3,
                "occurredAt": "2026-05-19T12:10:00.000Z",
                "computer": "WIN-SOC-01",
                "recordId": "3001",
                "data": {
                    "ProcessGuid": "{11111111-1111-1111-1111-111111111111}",
                    "ProcessId": "1200",
                    "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "User": r"FORTIDASHBOARD\analyst",
                    "Protocol": "tcp",
                    "SourceIp": "192.0.2.50",
                    "SourcePort": "54122",
                    "DestinationIp": "198.51.100.20",
                    "DestinationHostname": "suspicious.example",
                    "DestinationPort": "443",
                },
            },
            {
                "eventId": 22,
                "occurredAt": "2026-05-19T12:10:01.000Z",
                "computer": "WIN-SOC-01",
                "recordId": "3002",
                "data": {
                    "ProcessGuid": "{11111111-1111-1111-1111-111111111111}",
                    "ProcessId": "1200",
                    "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "User": r"FORTIDASHBOARD\analyst",
                    "QueryName": "suspicious.example",
                    "QueryStatus": "0",
                    "QueryResults": "198.51.100.20;",
                },
            },
        ],
    )

    assert payloads == [
        {
            "endpointId": "end_win_01",
            "eventType": "sysmon.network_connection",
            "occurredAt": "2026-05-19T12:10:00.000Z",
            "hostname": "WIN-SOC-01",
            "ipAddresses": ["192.0.2.50"],
            "currentUser": r"FORTIDASHBOARD\analyst",
            "attributes": {
                "source": "agent_private.sysmon",
                "sysmonEventId": 3,
                "recordId": "3001",
                "processGuid": "{11111111-1111-1111-1111-111111111111}",
                "processId": 1200,
                "image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "processName": "chrome.exe",
                "username": r"FORTIDASHBOARD\analyst",
                "protocol": "tcp",
                "sourceIp": "192.0.2.50",
                "sourcePort": 54122,
                "destinationIp": "198.51.100.20",
                "destinationHostname": "suspicious.example",
                "destinationPort": 443,
                "ioc": {
                    "type": "ip",
                    "value": "198.51.100.20",
                    "relatedDomain": "suspicious.example",
                },
            },
        },
        {
            "endpointId": "end_win_01",
            "eventType": "sysmon.dns_query",
            "occurredAt": "2026-05-19T12:10:01.000Z",
            "hostname": "WIN-SOC-01",
            "ipAddresses": ["192.0.2.50"],
            "currentUser": r"FORTIDASHBOARD\analyst",
            "attributes": {
                "source": "agent_private.sysmon",
                "sysmonEventId": 22,
                "recordId": "3002",
                "processGuid": "{11111111-1111-1111-1111-111111111111}",
                "processId": 1200,
                "image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "processName": "chrome.exe",
                "username": r"FORTIDASHBOARD\analyst",
                "queryName": "suspicious.example",
                "queryStatus": "0",
                "queryResults": ["198.51.100.20"],
                "ioc": {"type": "domain", "value": "suspicious.example"},
            },
        },
    ]


def test_sysmon_command_prints_normalized_payloads_without_posting(monkeypatch, capsys):
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
            "hostname": "WIN-SOC-01",
            "username": "analyst",
            "os": "Windows",
        },
    )
    monkeypatch.setattr(
        cli,
        "collect_sysmon_events",
        lambda limit=50: [
            {
                "eventId": 22,
                "occurredAt": "2026-05-19T12:10:01.000Z",
                "computer": "WIN-SOC-01",
                "recordId": "3002",
                "data": {
                    "ProcessId": "1200",
                    "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "User": r"FORTIDASHBOARD\analyst",
                    "QueryName": "suspicious.example",
                    "QueryStatus": "0",
                    "QueryResults": "198.51.100.20;",
                },
            }
        ],
    )

    main(["sysmon", "--endpoint-id", "end_win_01", "--limit", "10"])

    output = json.loads(capsys.readouterr().out)
    assert posted is False
    assert output[0]["eventType"] == "sysmon.dns_query"
    assert output[0]["attributes"]["ioc"] == {
        "type": "domain",
        "value": "suspicious.example",
    }


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


def test_run_command_launches_tui(monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "run_tui", lambda: calls.append("tui"))

    main(["run"])

    assert calls == ["tui"]


def test_run_headless_command_calls_foreground_runner(monkeypatch):
    calls = []

    def fake_run_agent(config, *, once=False):
        calls.append((config, once))

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    main(
        [
            "run-headless",
            "--api-url",
            "http://localhost:8000",
            "--endpoint-id",
            "end_win_lab",
            "--enrollment-token",
            "secret-token",
            "--heartbeat-interval",
            "1",
            "--connection-interval",
            "2",
            "--process-interval",
            "3",
            "--windows-security-interval",
            "4",
            "--windows-security-limit",
            "5",
            "--sysmon-interval",
            "6",
            "--sysmon-limit",
            "7",
            "--once",
        ]
    )

    assert len(calls) == 1
    config, once = calls[0]
    assert once is True
    assert config.api_url == "http://localhost:8000"
    assert config.endpoint_id == "end_win_lab"
    assert config.enrollment_token == "secret-token"
    assert config.heartbeat_interval == 1
    assert config.connection_interval == 2
    assert config.process_interval == 3
    assert config.windows_security_interval == 4
    assert config.windows_security_limit == 5
    assert config.sysmon_interval == 6
    assert config.sysmon_limit == 7


def test_status_command_queries_local_daemon(monkeypatch, capsys):
    class FakeControlClient:
        def __init__(self, *, base_url):
            assert base_url == "http://127.0.0.1:8765"

        def status(self):
            return {"endpointId": "end_win_01", "sentCount": 2}

    monkeypatch.setattr(cli, "AgentControlClient", FakeControlClient)

    main(["status"])

    assert json.loads(capsys.readouterr().out) == {
        "endpointId": "end_win_01",
        "sentCount": 2,
    }


def test_collect_now_command_queries_local_daemon(monkeypatch, capsys):
    class FakeControlClient:
        def __init__(self, *, base_url):
            assert base_url == "http://127.0.0.1:8765"

        def collect_now(self, kind):
            return {"posted": [kind]}

    monkeypatch.setattr(cli, "AgentControlClient", FakeControlClient)

    main(["collect-now", "processes"])

    assert json.loads(capsys.readouterr().out) == {"posted": ["processes"]}


def test_service_command_routes_to_windows_service(monkeypatch, capsys):
    calls: list[str] = []

    monkeypatch.setattr(
        cli.windows_service,
        "run_service_command",
        lambda action: calls.append(action) or {"service": "FortiDashboardAgent"},
    )

    main(["service", "status"])

    assert calls == ["status"]
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "service": "FortiDashboardAgent",
        "action": "status",
        "outcome": "success",
        "telemetry": {"sent": False, "reason": "agent config is incomplete"},
    }


def test_service_command_reports_failure_to_xdr(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.json"
    posted: list[dict] = []

    tui.save_config(
        tui.AgentPrivateConfig(
            api_url="http://192.168.204.1:8000",
            endpoint_id="enr_01",
            enrollment_token="secret-token",
        ),
        config_path,
    )
    monkeypatch.setattr(tui, "default_config_path", lambda: config_path)
    monkeypatch.setattr(
        cli,
        "_identity_context",
        lambda: (
            {
                "service": "agent_private",
                "hostname": "WIN-LAB-01",
                "username": "Administrator",
                "os": "Windows",
            },
            ["192.168.204.77"],
        ),
    )

    def fake_run_service_command(action):
        assert action == "start"
        print("Error starting service: The service did not respond in time.")
        return {"service": "FortiDashboardAgent", "action": "start"}

    def fake_post_endpoint_event(**kwargs):
        posted.append(kwargs)

    monkeypatch.setattr(cli.windows_service, "run_service_command", fake_run_service_command)
    monkeypatch.setattr(
        cli.windows_service,
        "service_status",
        lambda: {"service": "FortiDashboardAgent", "status": "stopped"},
    )
    monkeypatch.setattr(cli, "post_endpoint_event", fake_post_endpoint_event)
    monkeypatch.setattr(
        cli,
        "_management_diagnostics",
        lambda outcome, *, reason: {"reason": reason, "windows": {"serviceConfig": "captured"}},
    )

    main(["service", "start"])

    output = json.loads(capsys.readouterr().out)
    assert output["outcome"] == "failed"
    assert output["serviceStatus"] == {"service": "FortiDashboardAgent", "status": "stopped"}
    assert "did not respond" in output["stdout"]
    assert output["diagnostics"] == {
        "reason": "service.command",
        "windows": {"serviceConfig": "captured"},
    }
    assert output["telemetry"] == {"sent": True, "eventType": "health.signal"}
    assert len(posted) == 1
    assert posted[0]["api_url"] == "http://192.168.204.1:8000"
    assert posted[0]["enrollment_token"] == "secret-token"
    payload = posted[0]["payload"]
    assert payload["endpointId"] == "enr_01"
    assert payload["eventType"] == "health.signal"
    assert payload["health"] == "warning"
    assert payload["attributes"]["serviceAction"] == "start"
    assert payload["attributes"]["outcome"] == "failed"
    assert payload["attributes"]["diagnostics"]["windows"]["serviceConfig"] == "captured"


def test_task_command_reports_failure_to_xdr(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.json"
    posted: list[dict] = []

    tui.save_config(
        tui.AgentPrivateConfig(
            api_url="http://192.168.204.1:8000",
            endpoint_id="enr_01",
            enrollment_token="secret-token",
        ),
        config_path,
    )
    monkeypatch.setattr(tui, "default_config_path", lambda: config_path)
    monkeypatch.setattr(
        cli,
        "_identity_context",
        lambda: (
            {
                "service": "agent_private",
                "hostname": "WIN-LAB-01",
                "username": "Administrator",
                "os": "Windows",
            },
            ["192.168.204.77"],
        ),
    )
    monkeypatch.setattr(
        cli.windows_task,
        "run_task_command",
        lambda action: {
            "task": "FortiDashboardAgentDaemon",
            "action": action,
            "run": {"returnCode": 1, "stderr": "task not found"},
        },
    )
    monkeypatch.setattr(
        cli.windows_task,
        "task_status",
        lambda: {"task": "FortiDashboardAgentDaemon", "status": "missing"},
    )
    monkeypatch.setattr(
        cli,
        "_management_diagnostics",
        lambda outcome, *, reason: {"reason": reason, "windows": {"taskQuery": "captured"}},
    )
    monkeypatch.setattr(cli, "post_endpoint_event", lambda **kwargs: posted.append(kwargs))

    main(["task", "start"])

    output = json.loads(capsys.readouterr().out)
    assert output["outcome"] == "failed"
    assert output["diagnostics"]["reason"] == "task.start"
    assert output["telemetry"] == {"sent": True, "eventType": "health.signal"}
    payload = posted[0]["payload"]
    assert payload["attributes"]["source"] == "agent_private.windows_task"
    assert payload["attributes"]["taskAction"] == "start"
    assert payload["attributes"]["taskStatus"] == {
        "task": "FortiDashboardAgentDaemon",
        "status": "missing",
    }


def test_diagnostics_command_can_post_to_xdr(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.json"
    posted: list[dict] = []

    tui.save_config(
        tui.AgentPrivateConfig(
            api_url="http://192.168.204.1:8000",
            endpoint_id="enr_01",
            enrollment_token="secret-token",
        ),
        config_path,
    )
    monkeypatch.setattr(tui, "default_config_path", lambda: config_path)
    monkeypatch.setattr(
        cli,
        "_identity_context",
        lambda: (
            {
                "service": "agent_private",
                "hostname": "WIN-LAB-01",
                "username": "Administrator",
                "os": "Windows",
            },
            ["192.168.204.77"],
        ),
    )
    monkeypatch.setattr(
        cli,
        "_management_diagnostics",
        lambda outcome, *, reason: {"reason": reason, "config": {"safeSummary": {}}},
    )
    monkeypatch.setattr(cli, "post_endpoint_event", lambda **kwargs: posted.append(kwargs))

    main(["diagnostics", "--post", "--reason", "manual-test"])

    output = json.loads(capsys.readouterr().out)
    assert output["telemetry"] == {"sent": True, "eventType": "health.signal"}
    payload = posted[0]["payload"]
    assert payload["attributes"]["source"] == "agent_private.diagnostics"
    assert payload["attributes"]["reason"] == "manual-test"
    assert payload["attributes"]["diagnostics"]["reason"] == "manual-test"
