from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_create_fortigate_integration_never_returns_api_key():
    response = client.post(
        "/api/integrations/fortigate",
        headers=csrf_headers(),
        json={
            "name": "FortiGate Lab",
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload == {
        "id": "int_fgt_01",
        "type": "fortigate",
        "name": "FortiGate Lab",
        "status": "connected",
        "capabilities": ["system", "interfaces", "policies", "threat_logs"],
        "lastCheckedAt": "2026-04-26T20:30:00.000Z",
    }
    assert "apiKey" not in payload


def test_test_fortigate_connection_returns_device_metadata():
    response = client.post(
        "/api/integrations/fortigate/test",
        headers=csrf_headers(),
        json={
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "status": "connected",
        "device": {
            "hostname": "FGT-VM",
            "model": "FortiGate-VM64",
            "version": "v7.4.x",
        },
    }


def test_test_fortigate_connection_rejects_short_api_key():
    response = client.post(
        "/api/integrations/fortigate/test",
        headers=csrf_headers(),
        json={
            "host": "https://fortigate.local",
            "apiKey": "abc",
            "verifyTls": False,
        },
    )

    assert response.status_code == 422


def test_list_integrations_omits_api_key():
    response = client.get("/api/integrations")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "items": [
            {
                "id": "int_fgt_01",
                "type": "fortigate",
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "status": "connected",
                "lastCheckedAt": "2026-04-26T20:30:00.000Z",
            }
        ]
    }
    assert "apiKey" not in payload["items"][0]


def test_delete_integration_returns_contract_payload():
    response = client.delete(
        "/api/integrations/int_fgt_01",
        headers=csrf_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": "int_fgt_01"}


def test_widget_catalog_filters_to_fortigate_widgets():
    response = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [
        "fortigate-system-status",
        "fortigate-network-traffic",
        "fortigate-kpi-sessions",
        "fortigate-firewall-policies",
        "fortigate-top-threats",
        "fortigate-risk-posture",
        "fortigate-interface-health",
        "fortigate-recent-events",
        "fortigate-anomaly-highlights",
        "fortigate-top-source-ips",
    ]
    assert payload["items"][0]["defaultSize"] == {"w": 3, "h": 2}
    risk_posture = next(item for item in payload["items"] if item["id"] == "fortigate-risk-posture")
    assert risk_posture["template"] == "risk-summary"
    assert risk_posture["dataGroup"] == "risk"
    assert risk_posture["fieldBindings"] == {
        "score": "risk.score",
        "signals": "risk.signals",
    }


def test_fortigate_provider_data_fields_describe_powerbi_like_model():
    response = client.get("/api/providers/fortigate/data-fields")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "fortigate"
    assert [group["id"] for group in payload["groups"]] == [
        "system",
        "interfaces",
        "policies",
        "events",
        "risk",
    ]
    system_fields = payload["groups"][0]["fields"]
    assert system_fields[0] == {
        "id": "system.cpu",
        "label": "CPU Usage",
        "type": "number",
        "unit": "percent",
        "source": "fortigate-system-status",
        "recommendedVisuals": ["kpi", "gauge", "risk-summary"],
    }


def test_penguin_provider_data_fields_are_grouped_for_custom_visuals():
    response = client.get("/api/providers/siem_kowalski/data-fields")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "siem_kowalski"
    assert payload["groups"][0]["id"] == "incidents"
    assert payload["groups"][0]["category"] == "SIEM / Incidents"
    assert payload["groups"][0]["fields"][0] == {
        "id": "total",
        "label": "Open Incidents",
        "type": "number",
        "unit": "count",
        "source": "soc-incidents-by-severity",
        "recommendedVisuals": ["card", "gauge"],
    }


def test_soc_provider_data_fields_aggregate_penguin_categories():
    response = client.get("/api/providers/soc/data-fields")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "soc"
    assert {group["category"] for group in payload["groups"]} >= {
        "SIEM / Incidents",
        "XDR / Endpoints",
        "SOAR / Playbooks",
    }


def test_widget_data_returns_normalized_system_status():
    response = client.get(
        "/api/widgets/fortigate-system-status/data",
        params={"integrationId": "int_fgt_01"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "widgetId": "fortigate-system-status",
        "integrationId": "int_fgt_01",
        "refreshedAt": "2026-04-26T20:31:00.000Z",
        "status": "ready",
        "data": {
            "cpu": 12,
            "memory": 54,
            "sessions": 3812,
            "uptimeSeconds": 92420,
        },
        "meta": {
            "source": "fortigate",
            "cacheTtlSeconds": 2,
            "refreshIntervalSeconds": 2,
        },
    }


def test_mock_widget_data_returns_soc_enrichment_templates():
    for widget_id in (
        "fortigate-risk-posture",
        "fortigate-interface-health",
        "fortigate-recent-events",
        "fortigate-anomaly-highlights",
    ):
        response = client.get(
            f"/api/widgets/{widget_id}/data",
            params={"integrationId": "int_fgt_01"},
        )

        assert response.status_code == 200
        assert response.json()["widgetId"] == widget_id
        assert response.json()["integrationId"] == "int_fgt_01"
        assert response.json()["status"] == "ready"


def test_workspace_round_trip_contract():
    get_response = client.get("/api/workspaces/ws_default")

    assert get_response.status_code == 200
    assert get_response.json() == {
        "id": "ws_default",
        "name": "SOC Overview",
        "widgets": [
            {
                "instanceId": "w_01",
                "catalogId": "fortigate-system-status",
                "integrationId": "int_fgt_01",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
            }
        ],
    }

    put_response = client.put(
        "/api/workspaces/ws_default",
        headers=csrf_headers(),
        json={
            "name": "SOC Overview",
            "widgets": [
                {
                    "instanceId": "w_01",
                    "catalogId": "fortigate-system-status",
                    "integrationId": "int_fgt_01",
                    "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
                }
            ],
        },
    )

    assert put_response.status_code == 200
    assert put_response.json() == {
        "id": "ws_default",
        "version": 2,
        "updatedAt": "2026-04-26T20:32:00.000Z",
    }
