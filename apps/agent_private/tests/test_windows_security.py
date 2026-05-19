from __future__ import annotations

from agent_private.windows_security import collect_new_windows_security_events


def test_windows_security_cursor_initializes_without_replaying_backlog(tmp_path):
    state_path = tmp_path / "state.json"

    result = collect_new_windows_security_events(
        50,
        state_path=state_path,
        collector=lambda limit: [
            {"eventId": 4672, "recordId": "101"},
            {"eventId": 4672, "recordId": "100"},
        ],
    )

    assert result == []
    assert '"windowsSecurityLastRecordId": 101' in state_path.read_text()


def test_windows_security_cursor_returns_only_new_records(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"windowsSecurityLastRecordId": 100}')

    result = collect_new_windows_security_events(
        50,
        state_path=state_path,
        collector=lambda limit: [
            {"eventId": 4672, "recordId": "102"},
            {"eventId": 4625, "recordId": "101"},
            {"eventId": 4672, "recordId": "100"},
        ],
    )

    assert [event["recordId"] for event in result] == ["101", "102"]
    assert '"windowsSecurityLastRecordId": 102' in state_path.read_text()
