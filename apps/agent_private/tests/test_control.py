from __future__ import annotations

from agent_private.control import AgentControlClient, AgentControlServer, AgentControlState


def test_control_status_returns_redacted_runtime_state():
    state = AgentControlState(
        endpoint_id="end_win_01",
        started_at=100.0,
        sent_count=2,
        failed_count=1,
        last_event="heartbeat",
    )
    server = AgentControlServer(state=state, collect_now=lambda kind: {"posted": []})

    with server.running(port=0) as address:
        payload = AgentControlClient(
            base_url=f"http://{address.host}:{address.port}"
        ).status()

    assert payload["endpointId"] == "end_win_01"
    assert payload["sentCount"] == 2
    assert payload["failedCount"] == 1
    assert payload["lastEvent"] == "heartbeat"
    assert "token" not in repr(payload).lower()


def test_control_collect_now_posts_requested_kind():
    calls: list[str] = []
    state = AgentControlState(endpoint_id="end_win_01", started_at=100.0)
    server = AgentControlServer(
        state=state,
        collect_now=lambda kind: {"posted": [calls.append(kind) or kind]},
    )

    with server.running(port=0) as address:
        payload = AgentControlClient(
            base_url=f"http://{address.host}:{address.port}"
        ).collect_now("processes")

    assert calls == ["processes"]
    assert payload == {"posted": ["processes"]}
