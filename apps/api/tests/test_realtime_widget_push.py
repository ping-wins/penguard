from datetime import UTC, datetime, timedelta

from app.main import _fortigate_realtime_widget_snapshots, _syslog_realtime_events


class FakeFortiGateWidgetService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_widget_data(
        self,
        widget_id: str,
        integration_id: str,
        *,
        owner_user_id: str,
    ) -> dict:
        self.calls.append((widget_id, integration_id, owner_user_id))
        return {
            "widgetId": widget_id,
            "integrationId": integration_id,
            "refreshedAt": "2026-05-15T12:00:00.000Z",
            "status": "ready",
            "data": {
                "hostname": "FGT-LAB",
                "cpu": 7,
                "memory": 52,
                "sessions": 18,
            },
            "meta": {
                "source": "fortigate",
                "cacheTtlSeconds": 2,
                "refreshIntervalSeconds": 2,
            },
        }


def test_syslog_realtime_snapshot_includes_fortigate_system_status_widget():
    service = FakeFortiGateWidgetService()
    last_sent: dict[tuple[str, str], datetime] = {}

    snapshots = _fortigate_realtime_widget_snapshots(
        widget_service=service,
        owner_user_id="user_01",
        integration_id="int_fgt_01",
        now=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
        last_sent=last_sent,
        min_interval_seconds=0,
    )

    assert snapshots == [
        {
            "widgetId": "fortigate-system-status",
            "integrationId": "int_fgt_01",
            "refreshedAt": "2026-05-15T12:00:00.000Z",
            "status": "ready",
            "data": {
                "hostname": "FGT-LAB",
                "cpu": 7,
                "memory": 52,
                "sessions": 18,
            },
            "meta": {
                "source": "fortigate",
                "cacheTtlSeconds": 2,
                "refreshIntervalSeconds": 2,
            },
        }
    ]
    assert service.calls == [("fortigate-system-status", "int_fgt_01", "user_01")]


def test_syslog_realtime_snapshots_are_throttled_per_integration():
    service = FakeFortiGateWidgetService()
    last_sent: dict[tuple[str, str], datetime] = {}
    first_at = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)

    first = _fortigate_realtime_widget_snapshots(
        widget_service=service,
        owner_user_id="user_01",
        integration_id="int_fgt_01",
        now=first_at,
        last_sent=last_sent,
        min_interval_seconds=5,
    )
    second = _fortigate_realtime_widget_snapshots(
        widget_service=service,
        owner_user_id="user_01",
        integration_id="int_fgt_01",
        now=first_at + timedelta(seconds=2),
        last_sent=last_sent,
        min_interval_seconds=5,
    )
    third = _fortigate_realtime_widget_snapshots(
        widget_service=service,
        owner_user_id="user_01",
        integration_id="int_fgt_01",
        now=first_at + timedelta(seconds=5),
        last_sent=last_sent,
        min_interval_seconds=5,
    )

    assert first
    assert second == []
    assert third
    assert service.calls == [
        ("fortigate-system-status", "int_fgt_01", "user_01"),
        ("fortigate-system-status", "int_fgt_01", "user_01"),
    ]


def test_syslog_realtime_events_include_siem_domain_payloads():
    received_at = datetime(2026, 5, 18, 3, 30, tzinfo=UTC)
    event = {
        "id": "evt_waf_dos_01",
        "eventType": "waf.dos",
        "severity": "critical",
        "occurredAt": "2026-05-18T03:30:00Z",
        "entities": {"sourceIp": "10.10.10.10"},
        "attributes": {"action": "close", "ingestionMode": "fortigate_flow_inference"},
    }
    ticket = {
        "id": "inc_waf_dos_01",
        "ruleId": "fortiweb_dos_activity",
        "title": "FortiWeb DoS activity detected",
        "severity": "critical",
        "createdAt": "2026-05-18T03:30:00Z",
    }

    events = _syslog_realtime_events(
        owner_user_id="user_01",
        integration_id="int_fgt_01",
        event_id="evt_waf_dos_01",
        event=event,
        ticket=ticket,
        received_at=received_at,
        widget_snapshots=[],
    )

    assert [item["type"] for item in events] == [
        "fortigate.syslog.event",
        "soc.event.created",
        "soc.incident.created",
    ]
    assert events[1]["event"] == event
    assert events[2]["event"] == event
    assert events[2]["ticket"] == ticket
