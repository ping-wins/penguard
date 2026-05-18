import asyncio
import time
from datetime import UTC, datetime

from app.integrations.fortigate.syslog import (
    FortiGateSyslogForwarder,
    FortiGateSyslogProtocol,
    parse_fortigate_syslog,
    send_fortigate_syslog_probe,
    start_fortigate_syslog_udp_collector,
)


class RecordingSiemClient:
    def __init__(self):
        self.requests = []

    def request(self, method: str, path: str, **kwargs):
        self.requests.append((method, path, kwargs))
        event = {"id": "evt_siem_01", **kwargs["json"]}
        if path == "/events/ingest":
            return {
                "event": event,
                "incident": {
                    "id": "inc_siem_01",
                    "title": "FortiGate denied traffic burst",
                    "severity": "high",
                    "triageLevel": "T1",
                    "ticketStatus": "new",
                    "createdAt": "2026-05-15T12:00:00.000Z",
                },
            }
        return event


class SlowSiemClient(RecordingSiemClient):
    def __init__(self, *, delay_seconds: float):
        super().__init__()
        self.delay_seconds = delay_seconds

    def request(self, method: str, path: str, **kwargs):
        time.sleep(self.delay_seconds)
        return super().request(method, path, **kwargs)


class RecordingSyslogStatusRecorder:
    def __init__(self):
        self.calls = []

    def __call__(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        event: dict | None = None,
        ticket: dict | None = None,
    ):
        self.calls.append(
            {
                "ownerUserId": owner_user_id,
                "integrationId": integration_id,
                "eventId": event_id,
                "event": event,
                "ticket": ticket,
            }
        )


def test_parse_fortigate_traffic_syslog_maps_to_siem_event():
    line = (
        '<189>date=2026-05-14 time=22:32:01 devname="FGVMEVJAOUIR5F07" '
        'devid="FGVM01" type="traffic" subtype="forward" level="notice" '
        'srcip=192.0.2.10 dstip=10.10.20.10 srcport=43822 dstport=22 '
        'proto=6 service="SSH" action="deny" policyid=12 '
        'msg="Denied by forward policy check"'
    )

    event = parse_fortigate_syslog(line, integration_id="int_fgt_01")

    assert event == {
        "source": "fortigate.syslog",
        "eventType": "network.deny",
        "severity": "medium",
        "occurredAt": "2026-05-14T22:32:01Z",
        "entities": {
            "sourceIp": "192.0.2.10",
            "destinationIp": "10.10.20.10",
            "integrationId": "int_fgt_01",
            "deviceName": "FGVMEVJAOUIR5F07",
        },
        "attributes": {
            "originKind": "fortigate.syslog",
            "action": "deny",
            "type": "traffic",
            "subtype": "forward",
            "level": "notice",
            "service": "SSH",
            "policyId": "12",
            "sourcePort": 43822,
            "destinationPort": 22,
            "protocol": "6",
            "message": "Denied by forward policy check",
            "count": 1,
            "raw": line,
        },
    }


def test_parse_fortigate_syslog_prefers_eventtime_for_utc_occurrence():
    line = (
        '<189>date=2026-05-17 time=21:37:24 tz="-0700" '
        'eventtime=1779079044198123665 devname="FGVMEVJAOUIR5F07" '
        'devid="FGVM01" type="traffic" subtype="forward" level="notice" '
        'srcip=192.0.2.10 dstip=198.51.100.30 srcport=39336 dstport=80 '
        'proto=6 service="HTTP" action="close" policyid=2'
    )

    event = parse_fortigate_syslog(line, integration_id="int_fgt_01")

    assert event["occurredAt"] == "2026-05-18T04:37:24Z"


def test_parse_fortigate_syslog_applies_timezone_offset_without_eventtime():
    line = (
        '<189>date=2026-05-17 time=21:37:24 tz="-0700" '
        'devname="FGVMEVJAOUIR5F07" devid="FGVM01" type="traffic" '
        'subtype="forward" level="notice" srcip=192.0.2.10 '
        'dstip=198.51.100.30 service="HTTP" action="close"'
    )

    event = parse_fortigate_syslog(line, integration_id="int_fgt_01")

    assert event["occurredAt"] == "2026-05-18T04:37:24Z"


def test_parse_fortigate_event_lockout_maps_to_failed_login_burst():
    line = (
        '<189>date=2026-05-14 time=22:36:00 devname="FGT-LAB" '
        'type="event" subtype="system" level="alert" user="admin" '
        'srcip=192.0.2.44 action="login" status="failed" '
        'msg="Administrator admin login disabled from 192.0.2.44 because of 3 bad attempts"'
    )

    event = parse_fortigate_syslog(line, integration_id="int_fgt_01")

    assert event["eventType"] == "auth.failed_login"
    assert event["severity"] == "critical"
    assert event["entities"]["sourceIp"] == "192.0.2.44"
    assert event["attributes"]["user"] == "admin"
    assert event["attributes"]["count"] == 3
    assert event["attributes"]["lockout"] is True
    assert event["attributes"]["attackType"] == "brute_force"


def test_syslog_forwarder_posts_each_datagram_to_siem_without_polling():
    siem = RecordingSiemClient()
    recorder = RecordingSyslogStatusRecorder()
    forwarder = FortiGateSyslogForwarder(
        siem_client=siem,
        integration_resolver=lambda _addr, _fields: {
            "integrationId": "int_fgt_01",
            "ownerUserId": "user_01",
        },
        status_recorder=recorder,
        now=lambda: datetime(2026, 5, 14, 22, 33, tzinfo=UTC),
    )
    line = (
        'date=2026-05-14 time=22:33:00 type="traffic" subtype="forward" '
        'level="information" srcip=192.0.2.10 dstip=10.10.20.10 '
        'action="accept" service="PING" msg="Allowed by policy"'
    )

    result = forwarder.handle_datagram(line.encode(), addr=("192.0.2.118", 54123))

    assert result["status"] == "forwarded"
    assert result["integrationId"] == "int_fgt_01"
    assert result["eventId"] == "evt_siem_01"
    assert result["event"]["id"] == "evt_siem_01"
    assert len(siem.requests) == 1
    method, path, kwargs = siem.requests[0]
    assert (method, path) == ("POST", "/events/ingest")
    posted = kwargs["json"]
    assert posted["source"] == "fortigate.syslog"
    assert posted["eventType"] == "network.event"
    assert posted["attributes"]["transport"] == "udp"
    assert posted["attributes"]["collectorSourceIp"] == "192.0.2.118"
    assert recorder.calls == [
        {
            "ownerUserId": "user_01",
            "integrationId": "int_fgt_01",
            "eventId": "evt_siem_01",
            "event": {
                "id": "evt_siem_01",
                **posted,
            },
            "ticket": {
                "id": "inc_siem_01",
                "title": "FortiGate denied traffic burst",
                "severity": "high",
                "triageLevel": "T1",
                "ticketStatus": "new",
                "createdAt": "2026-05-15T12:00:00.000Z",
            },
        }
    ]


def test_syslog_protocol_does_not_block_socket_callback_on_siem_request():
    async def scenario():
        siem = SlowSiemClient(delay_seconds=0.2)
        recorder = RecordingSyslogStatusRecorder()
        forwarder = FortiGateSyslogForwarder(
            siem_client=siem,
            integration_resolver=lambda _addr, _fields: {
                "integrationId": "int_fgt_01",
                "ownerUserId": "user_01",
            },
            status_recorder=recorder,
            now=lambda: datetime(2026, 5, 14, 22, 33, tzinfo=UTC),
        )
        protocol = FortiGateSyslogProtocol(forwarder)
        protocol.connection_made(None)
        line = (
            'date=2026-05-14 time=22:33:00 type="traffic" subtype="forward" '
            'level="information" srcip=192.0.2.10 dstip=10.10.20.10 '
            'action="accept" service="PING" msg="Allowed by policy"'
        )

        started_at = time.perf_counter()
        protocol.datagram_received(line.encode(), ("192.0.2.118", 54123))
        callback_elapsed = time.perf_counter() - started_at
        for _ in range(50):
            if recorder.calls:
                break
            await asyncio.sleep(0.01)
        protocol.connection_lost(None)

        return callback_elapsed, siem.requests, recorder.calls

    callback_elapsed, requests, calls = asyncio.run(scenario())

    assert callback_elapsed < 0.05
    assert len(requests) == 1
    assert calls[0]["eventId"] == "evt_siem_01"


def test_udp_collector_self_probe_exercises_parser_forwarder_and_status_recorder():
    async def scenario():
        siem = RecordingSiemClient()
        recorder = RecordingSyslogStatusRecorder()
        forwarder = FortiGateSyslogForwarder(
            siem_client=siem,
            integration_resolver=lambda _addr, _fields: {
                "integrationId": "int_fgt_01",
                "ownerUserId": "user_01",
            },
            status_recorder=recorder,
            now=lambda: datetime(2026, 5, 14, 22, 40, tzinfo=UTC),
        )
        transport = await start_fortigate_syslog_udp_collector(
            host="127.0.0.1",
            port=0,
            forwarder=forwarder,
        )
        try:
            host, port = transport.get_extra_info("sockname")[:2]
            probe = await send_fortigate_syslog_probe(
                host=host,
                port=port,
                integration_id="int_fgt_01",
            )
            for _ in range(20):
                if recorder.calls:
                    break
                await asyncio.sleep(0.01)
        finally:
            transport.close()

        return probe, siem.requests, recorder.calls

    probe, requests, calls = asyncio.run(scenario())

    assert probe["sent"] is True
    assert probe["collectorHost"] == "127.0.0.1"
    assert probe["integrationId"] == "int_fgt_01"
    assert len(requests) == 1
    posted = requests[0][2]["json"]
    assert posted["eventType"] == "network.event"
    assert posted["attributes"]["probe"] is True
    assert posted["attributes"]["originKind"] == "fortigate.syslog"
    assert calls == [
        {
            "ownerUserId": "user_01",
            "integrationId": "int_fgt_01",
            "eventId": "evt_siem_01",
            "event": {
                "id": "evt_siem_01",
                **posted,
            },
            "ticket": {
                "id": "inc_siem_01",
                "title": "FortiGate denied traffic burst",
                "severity": "high",
                "triageLevel": "T1",
                "ticketStatus": "new",
                "createdAt": "2026-05-15T12:00:00.000Z",
            },
        }
    ]
