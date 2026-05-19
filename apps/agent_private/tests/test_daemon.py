from __future__ import annotations

from agent_private.daemon import AgentDaemon
from agent_private.runner import AgentRunConfig


def identity() -> dict[str, str]:
    return {
        "service": "agent_private",
        "hostname": "WIN-LAB-01",
        "username": "FORTIDASHBOARD\\Administrator",
        "os": "Windows",
    }


def test_daemon_collect_now_posts_requested_payloads():
    posted: list[dict] = []
    daemon = AgentDaemon(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_01",
            enrollment_token="secret-token",
        ),
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [{"pid": 1, "name": "lsass.exe"}],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
    )

    result = daemon.collect_now("processes")

    assert result["posted"] == ["process.snapshot"]
    assert posted[0]["eventType"] == "process.snapshot"
    assert daemon.status()["sentCount"] == 1
    assert "secret-token" not in repr(daemon.status())


def test_daemon_reports_post_failure_without_revealing_token():
    def failing_post(**kwargs):
        raise RuntimeError(f"rejected {kwargs['enrollment_token']}")

    daemon = AgentDaemon(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_01",
            enrollment_token="secret-token",
        ),
        post=failing_post,
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
    )

    result = daemon.collect_now("heartbeat")

    assert result["posted"] == []
    assert result["failed"] == [{"eventType": "heartbeat", "error": "rejected [redacted]"}]
    assert daemon.status()["failedCount"] == 1


def test_daemon_claims_remote_collect_now_action_and_reports_result():
    posted: list[dict] = []

    class FakeActionClient:
        def __init__(self) -> None:
            self.reported: list[tuple[str, str, dict]] = []

        def claim_next(self, endpoint_id: str):
            assert endpoint_id == "end_win_01"
            return {
                "id": "act_01",
                "kind": "collect_now",
                "parameters": {"kind": "heartbeat"},
            }

        def report_result(self, endpoint_id: str, action_id: str, *, status: str, result: dict):
            self.reported.append((endpoint_id, action_id, {"status": status, "result": result}))

    action_client = FakeActionClient()
    daemon = AgentDaemon(
        AgentRunConfig(
            api_url="http://localhost:8000",
            endpoint_id="end_win_01",
            enrollment_token="secret-token",
        ),
        post=lambda **kwargs: posted.append(kwargs["payload"]),
        identity_provider=identity,
        ip_provider=lambda: ["192.168.56.10"],
        process_collector=lambda limit=None: [],
        connection_collector=lambda: [],
        windows_security_collector=lambda limit=50: [],
    )

    processed = daemon.process_remote_action(action_client)

    assert processed is True
    assert [payload["eventType"] for payload in posted] == ["heartbeat"]
    assert action_client.reported == [
        (
            "end_win_01",
            "act_01",
            {
                "status": "completed",
                "result": {"posted": ["heartbeat"], "failed": []},
            },
        )
    ]
