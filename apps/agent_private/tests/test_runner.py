from __future__ import annotations

from agent_private.runner import AgentRunConfig, run_agent


def identity() -> dict[str, str]:
    return {
        "service": "agent_private",
        "hostname": "WIN-LAB-01",
        "username": "FORTIDASHBOARD\\Administrator",
        "os": "Windows",
    }


def test_run_agent_once_posts_core_payloads_without_windows_security():
    posted: list[dict] = []
    logs: list[str] = []

    run_agent(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_lab",
            enrollment_token="secret-token",
        ),
        once=True,
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        log=logs.append,
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [{"pid": 100, "name": "lsass.exe"}],
        connection_collector=lambda: [
            {
                "fd": -1,
                "family": "AF_INET",
                "type": "SOCK_STREAM",
                "localAddress": {"ip": "192.168.56.10", "port": 50000},
                "remoteAddress": {"ip": "203.0.113.10", "port": 443},
                "status": "ESTABLISHED",
                "pid": 100,
            }
        ],
        windows_security_collector=lambda limit=50: [
            {"eventId": 4625, "recordId": "1", "data": {}}
        ],
    )

    assert [payload["eventType"] for payload in posted] == [
        "heartbeat",
        "connection.snapshot",
        "process.snapshot",
    ]
    assert posted[0]["endpointId"] == "end_win_lab"
    assert posted[0]["hostname"] == "WIN-LAB-01"
    assert posted[0]["ipAddresses"] == ["192.168.56.10"]
    assert all("secret-token" not in row for row in logs)


def test_run_agent_once_posts_windows_security_when_enabled():
    posted: list[dict] = []

    run_agent(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_lab",
            enrollment_token="secret-token",
            windows_security_interval=60,
            windows_security_limit=10,
        ),
        once=True,
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        log=lambda message: None,
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [
            {
                "eventId": 4625,
                "occurredAt": "2026-05-13T18:00:00.000Z",
                "computer": "WIN-LAB-01",
                "recordId": "1",
                "data": {
                    "TargetUserName": "felipe",
                    "TargetDomainName": "FORTIDASHBOARD",
                    "IpAddress": "192.0.2.10",
                },
            }
        ],
    )

    assert [payload["eventType"] for payload in posted] == [
        "heartbeat",
        "connection.snapshot",
        "process.snapshot",
        "auth.failed_login",
    ]
    assert posted[-1]["attributes"]["windowsEventId"] == 4625


def test_run_agent_once_posts_sysmon_when_enabled():
    posted: list[dict] = []

    run_agent(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_lab",
            enrollment_token="secret-token",
            sysmon_interval=60,
            sysmon_limit=10,
        ),
        once=True,
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        log=lambda message: None,
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
        sysmon_collector=lambda limit=50: [
            {
                "eventId": 22,
                "occurredAt": "2026-05-19T12:10:01.000Z",
                "computer": "WIN-LAB-01",
                "recordId": "3002",
                "data": {
                    "ProcessId": "1200",
                    "Image": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "User": r"FORTIDASHBOARD\Administrator",
                    "QueryName": "suspicious.example",
                    "QueryStatus": "0",
                    "QueryResults": "198.51.100.20;",
                },
            }
        ],
    )

    assert [payload["eventType"] for payload in posted] == [
        "heartbeat",
        "connection.snapshot",
        "process.snapshot",
        "sysmon.dns_query",
    ]
    assert posted[-1]["attributes"]["sysmonEventId"] == 22
    assert posted[-1]["attributes"]["ioc"] == {
        "type": "domain",
        "value": "suspicious.example",
    }


def test_run_agent_logs_post_failures_without_revealing_token():
    logs: list[str] = []

    def failing_post(**kwargs):
        raise RuntimeError(f"backend rejected {kwargs['enrollment_token']}")

    run_agent(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_lab",
            enrollment_token="super-secret-token",
        ),
        once=True,
        post=failing_post,
        log=logs.append,
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
    )

    joined = "\n".join(logs)
    assert "post failed" in joined
    assert "super-secret-token" not in joined
    assert "[redacted]" in joined
