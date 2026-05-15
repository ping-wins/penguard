import json

import httpx
import pytest

from app.integrations.fortigate.client import FortiGateApiClient, FortiGateApiError
from app.integrations.fortigate.normalizers import (
    normalize_interfaces,
    normalize_policies,
    normalize_system_status,
    normalize_threat_logs,
)


def test_fortigate_client_uses_bearer_token_and_unwraps_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-token"
        assert request.url.path == "/api/v2/monitor/system/status"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "serial": "FGVMTEST",
                "version": "v7.6.6",
                "build": 3652,
                "uptime": 92420,
                "results": {
                    "hostname": "FGT-VM",
                    "model_name": "FortiGate-VM64",
                },
            },
        )

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_system_status() == {
        "hostname": "FGT-VM",
        "model_name": "FortiGate-VM64",
        "serial": "FGVMTEST",
        "version": "v7.6.6",
        "build": 3652,
        "uptime": 92420,
    }


def test_fortigate_client_does_not_merge_envelope_metadata_into_interface_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/monitor/system/interface"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "serial": "FGVMTEST",
                "version": "v7.6.6",
                "results": {
                    "port1": {
                        "id": "port1",
                        "name": "port1",
                        "ip": "192.0.2.118",
                        "link": True,
                    }
                },
            },
        )

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_interface_status() == {
        "port1": {
            "id": "port1",
            "name": "port1",
            "ip": "192.0.2.118",
            "link": True,
        }
    }


def test_fortigate_client_reads_web_ui_state_for_reboot_timestamp():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/monitor/web-ui/state"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "results": {
                    "snapshot_utc_time": 1777477582000,
                    "utc_last_reboot": 1777470648000,
                },
            },
        )

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_web_ui_state() == {
        "snapshot_utc_time": 1777477582000,
        "utc_last_reboot": 1777470648000,
    }


def test_fortigate_client_first_cut_only_uses_read_only_get_requests():
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/v2/monitor/system/status":
            return httpx.Response(200, json={"status": "success", "results": {}})
        if request.url.path == "/api/v2/monitor/system/performance/status":
            return httpx.Response(200, json={"status": "success", "results": {}})
        if request.url.path == "/api/v2/monitor/system/resource/usage":
            return httpx.Response(200, json={"status": "success", "results": {}})
        if request.url.path == "/api/v2/monitor/system/interface":
            return httpx.Response(200, json={"status": "success", "results": {}})
        if request.url.path == "/api/v2/monitor/web-ui/state":
            return httpx.Response(200, json={"status": "success", "results": {}})
        return httpx.Response(200, json={"status": "success", "results": []})

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    client.get_system_status()
    client.get_performance_status()
    client.get_resource_usage(resource="session")
    client.get_interface_status()
    client.get_web_ui_state()
    client.get_interfaces()
    client.get_policies()
    client.get_threat_logs(limit=25)

    assert requests == [
        ("GET", "/api/v2/monitor/system/status"),
        ("GET", "/api/v2/monitor/system/performance/status"),
        ("GET", "/api/v2/monitor/system/resource/usage"),
        ("GET", "/api/v2/monitor/system/interface"),
        ("GET", "/api/v2/monitor/web-ui/state"),
        ("GET", "/api/v2/cmdb/system/interface"),
        ("GET", "/api/v2/cmdb/firewall/policy"),
        ("GET", "/api/v2/log/memory/ips"),
    ]


def test_fortigate_client_creates_owned_address_object():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path == "/api/v2/cmdb/firewall/address":
            body = json.loads(request.content.decode())
            assert body == {
                "name": "FD_ADDR_192_0_2_50",
                "subnet": "192.0.2.50 255.255.255.255",
                "comment": "FortiDashboard owned temporary block object",
            }
            return httpx.Response(
                200,
                json={"status": "success", "mkey": "FD_ADDR_192_0_2_50"},
            )
        return httpx.Response(404, json={"status": "error"})

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    result = client.create_address_object(
        name="FD_ADDR_192_0_2_50",
        subnet="192.0.2.50 255.255.255.255",
        comment="FortiDashboard owned temporary block object",
    )

    assert result["status"] == "success"
    assert requests[0].headers["authorization"] == "Bearer secret-token"


def test_fortigate_client_creates_firewall_policy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v2/cmdb/firewall/policy":
            body = json.loads(request.content.decode())
            assert body["name"] == "FD_TMP_BLOCK_192_0_2_50"
            assert body["action"] == "deny"
            assert body["logtraffic"] == "all"
            assert body["srcaddr"] == [{"name": "FD_ADDR_192_0_2_50"}]
            return httpx.Response(200, json={"status": "success", "mkey": 42})
        return httpx.Response(404, json={"status": "error"})

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    result = client.create_firewall_policy(
        {
            "name": "FD_TMP_BLOCK_192_0_2_50",
            "action": "deny",
            "logtraffic": "all",
            "srcaddr": [{"name": "FD_ADDR_192_0_2_50"}],
            "dstaddr": [{"name": "all"}],
            "service": [{"name": "ALL"}],
            "schedule": "always",
            "srcintf": [{"name": "port2"}],
            "dstintf": [{"name": "port3"}],
            "status": "enable",
            "comments": "FortiDashboard owned temporary block",
        }
    )

    assert result["mkey"] == 42


def test_fortigate_client_includes_response_excerpt_for_http_errors():
    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                500,
                json={"status": "error", "error": -3, "message": "name size[35] exceeded"},
            )
        ),
    )

    with pytest.raises(FortiGateApiError, match=r"HTTP 500.*name size\[35\] exceeded"):
        client.create_firewall_policy(
            {
                "name": "FD_LAB_ALLOW_NAME_THAT_IS_TOO_LONG_FOR_FORTIOS",
                "action": "accept",
                "logtraffic": "all",
            }
        )


def test_fortigate_client_raises_for_fortios_error_status():
    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"status": "error", "http_status": 403, "error": -3},
            )
        ),
    )

    with pytest.raises(FortiGateApiError, match="FortiGate API returned error status"):
        client.get_system_status()


def test_fortigate_client_rejects_empty_api_key_before_network_call():
    with pytest.raises(ValueError, match="api_key is required"):
        FortiGateApiClient(
            host="https://fortigate.local",
            api_key="",
            verify_tls=False,
        )


def test_normalize_system_status_for_widget_and_connection_payloads():
    normalized = normalize_system_status(
        {
            "hostname": "FGT-VM",
            "model_name": "FortiGate-VM64",
            "version": "v7.4.3",
            "serial": "FGVMTEST",
            "cpu": 7,
            "mem": 48,
            "current_sessions": 3812,
            "uptime": 92420,
        }
    )

    assert normalized == {
        "hostname": "FGT-VM",
        "model": "FortiGate-VM64",
        "version": "v7.4.3",
        "serial": "FGVMTEST",
        "cpu": 7,
        "memory": 48,
        "sessions": 3812,
        "uptimeSeconds": 92420,
    }


def test_normalize_system_status_accepts_real_fortios_performance_payloads():
    normalized = normalize_system_status(
        {
            "hostname": "FGVMEVJAOUIR5F07",
            "model": "FGVM64",
            "model_name": "FortiGate",
            "model_number": "VM64",
            "serial": "FGVMEVJAOUIR5F07",
            "version": "v7.6.6",
            "build": 3652,
        },
        performance={
            "cpu": {"idle": 97, "iowait": 0, "nice": 0, "system": 1, "user": 2},
            "mem": {
                "free": 758415360,
                "freeable": 383713280,
                "total": 2091188224,
                "used": 949059584,
            },
        },
        resource_usage={"session": [{"current": 15}]},
    )

    assert normalized == {
        "hostname": "FGVMEVJAOUIR5F07",
        "model": "FortiGate",
        "version": "v7.6.6",
        "serial": "FGVMEVJAOUIR5F07",
        "build": 3652,
        "cpu": 3,
        "memory": 45,
        "sessions": 15,
        "uptimeSeconds": None,
    }


def test_normalize_system_status_reads_fortios_performance_uptime_text():
    normalized = normalize_system_status(
        {
            "hostname": "FGT-VM",
            "model_name": "FortiGate",
            "version": "v7.6.6",
        },
        performance={
            "cpu": {"idle": 97},
            "mem": {"used": 1024, "total": 2048},
            "uptime": "1 days, 1 hours, 40 minutes, 20 seconds",
        },
        resource_usage={"session": [{"current": 15}]},
    )

    assert normalized["uptimeSeconds"] == 92420


def test_normalize_system_status_derives_uptime_from_web_ui_state_reboot_time():
    normalized = normalize_system_status(
        {
            "hostname": "FGT-VM",
            "model_name": "FortiGate",
            "version": "v7.6.6",
        },
        performance={
            "cpu": {"idle": 97},
            "mem": {"used": 1024, "total": 2048},
        },
        resource_usage={"session": [{"current": 15}]},
        web_ui_state={
            "snapshot_utc_time": 1777477582000,
            "utc_last_reboot": 1777470648000,
        },
    )

    assert normalized["uptimeSeconds"] == 6934


def test_normalize_interfaces_policies_and_threat_logs():
    assert normalize_interfaces(
        [
            {
                "name": "port1",
                "alias": "WAN",
                "status": "up",
                "ip": "192.0.2.118 255.255.255.0",
                "role": "wan",
                "type": "physical",
            }
        ]
    ) == [
        {
            "id": "port1",
            "name": "port1",
            "alias": "WAN",
            "status": "up",
            "ip": "192.0.2.118",
            "role": "wan",
            "type": "physical",
            "rxBytes": 0,
            "txBytes": 0,
            "rxPackets": 0,
            "txPackets": 0,
        }
    ]

    assert normalize_policies(
        [
            {
                "policyid": 1,
                "name": "LAN to WAN",
                "status": "enable",
                "action": "accept",
                "srcintf": [{"name": "lan"}],
                "dstintf": [{"name": "wan"}],
                "service": [{"name": "HTTPS"}],
                "schedule": "always",
            },
            {
                "policyid": 42,
                "name": "FD_TMP_BLOCK_32FD0707AD9A",
                "status": "enable",
                "action": "deny",
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "FD_ADDR_10_10_10_10"}],
                "dstaddr": [{"name": "FD_ADDR_10_10_20_10"}],
                "service": [{"name": "ALL"}],
                "schedule": "always",
                "logtraffic": "all",
                "comments": "FortiDashboard owned temporary block policy",
            },
        ]
    ) == [
        {
            "id": "1",
            "name": "LAN to WAN",
            "status": "enabled",
            "action": "accept",
            "sourceInterfaces": ["lan"],
            "destinationInterfaces": ["wan"],
            "services": ["HTTPS"],
            "schedule": "always",
            "sourceAddresses": [],
            "destinationAddresses": [],
            "logging": "",
            "comments": "",
            "isBlocking": False,
            "isFortiDashboardOwned": False,
            "policyKind": "standard",
        },
        {
            "id": "42",
            "name": "FD_TMP_BLOCK_32FD0707AD9A",
            "status": "enabled",
            "action": "deny",
            "sourceInterfaces": ["port2"],
            "destinationInterfaces": ["port3"],
            "services": ["ALL"],
            "schedule": "always",
            "sourceAddresses": ["FD_ADDR_10_10_10_10"],
            "destinationAddresses": ["FD_ADDR_10_10_20_10"],
            "logging": "all",
            "comments": "FortiDashboard owned temporary block policy",
            "isBlocking": True,
            "isFortiDashboardOwned": True,
            "policyKind": "temporary_block",
        }
    ]

    assert normalize_threat_logs(
        [
            {
                "itime": 1777234800,
                "type": "utm",
                "subtype": "ips",
                "severity": "high",
                "srcip": "10.0.0.10",
                "dstip": "203.0.113.10",
                "action": "blocked",
                "msg": "IPS signature matched",
            }
        ]
    ) == [
        {
            "id": "1777234800-10.0.0.10-203.0.113.10-ips",
            "timestamp": "2026-04-26T20:20:00Z",
            "type": "utm",
            "subtype": "ips",
            "severity": "high",
            "sourceIp": "10.0.0.10",
            "destinationIp": "203.0.113.10",
            "action": "blocked",
            "message": "IPS signature matched",
        }
    ]


def test_normalize_interfaces_uses_fortios_dict_key_when_name_is_missing():
    assert normalize_interfaces(
        {
            "port1": {
                "id": "port1",
                "ip": "192.0.2.118",
                "link": True,
                "rx_bytes": 8304525,
                "tx_bytes": 6185442,
            }
        }
    ) == [
        {
            "id": "port1",
            "name": "port1",
            "alias": "",
            "status": "up",
            "ip": "192.0.2.118",
            "role": "unknown",
            "type": "unknown",
            "rxBytes": 8304525,
            "txBytes": 6185442,
            "rxPackets": 0,
            "txPackets": 0,
        }
    ]
