from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_ai_tool_registry_lists_safe_dashboard_tools():
    client = TestClient(app)

    response = client.get("/api/ai/tools")

    assert response.status_code == 200
    payload = response.json()
    tool_names = {item["name"] for item in payload["items"]}
    assert tool_names >= {
        "list_data_fields",
        "draft_widget",
        "validate_widget",
        "simulate_widget_data",
        "draft_containment_playbook",
    }
    draft_widget = next(item for item in payload["items"] if item["name"] == "draft_widget")
    assert draft_widget["category"] == "workspace"
    assert draft_widget["requiresConfirmation"] is True
    assert draft_widget["destructive"] is False
    assert draft_widget["timeoutSeconds"] == 3
    assert draft_widget["inputSchema"]["required"] == ["provider", "visualType", "fieldIds"]
    assert draft_widget["outputSchema"]["properties"]["status"]["const"] == "draft"
    assert all(item["destructive"] is False for item in payload["items"])


def test_ai_status_reports_pydantic_ai_cockpit_runtime():
    client = TestClient(app)

    response = client.get("/api/ai/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "scripted"
    assert payload["runtime"] == "pydantic_ai"
    assert payload["ready"] is True


def test_ai_chat_uses_cockpit_agent_and_audits_available_tools():
    client = TestClient(app)

    response = client.post(
        "/api/ai/chat",
        headers=csrf_headers(client),
        json={"messages": [{"role": "user", "content": "Quais tools voce pode usar?"}]},
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="ai.chat")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "pydantic_ai.scripted"
    assert payload["runtime"] == "pydantic_ai"
    assert "draft_widget" in payload["reply"]
    assert audit["items"][0]["details"]["runtime"] == "pydantic_ai"
    assert audit["items"][0]["details"]["toolCount"] >= 5


def test_ai_chat_can_draft_widget_with_internal_tool():
    client = TestClient(app)

    response = client.post(
        "/api/ai/chat",
        headers=csrf_headers(client),
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Crie um card usando o campo system.cpu do FortiGate",
                }
            ]
        },
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(action="ai.chat")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "pydantic_ai.scripted"
    assert "CPU Usage" in payload["reply"]
    assert "draft_widget" in payload["reply"]
    assert "confirme" in payload["reply"].lower()
    assert payload["widgetDrafts"] == [
        {
            "toolName": "draft_widget",
            "status": "draft",
            "requiresConfirmation": True,
            "draft": {
                "status": "draft",
                "provider": "fortigate",
                "integrationId": None,
                "visualType": "card",
                "title": "CPU Usage",
                "fieldBindings": [
                    {
                        "fieldId": "system.cpu",
                        "label": "CPU Usage",
                        "type": "number",
                        "unit": "percent",
                        "source": "fortigate-system-status",
                        "provider": "fortigate",
                        "integrationId": None,
                    }
                ],
                "layout": {"w": 2, "h": 2},
                "settings": {"aggregation": "latest"},
            },
            "preview": {
                "source": "simulation",
                "values": {"system.cpu": 0},
            },
            "validation": {"valid": True, "warnings": [], "errors": []},
        }
    ]
    assert audit["items"][0]["details"]["usedTools"] == ["draft_widget"]
    assert audit["items"][0]["details"]["widgetDraftCount"] == 1


def test_draft_widget_tool_returns_validated_draft_without_persisting():
    client = TestClient(app)

    response = client.post(
        "/api/ai/tools/draft-widget",
        headers=csrf_headers(client),
        json={
            "provider": "fortigate",
            "integrationId": "int_fgt_01",
            "visualType": "card",
            "fieldIds": ["system.cpu"],
            "title": "CPU usage",
        },
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.widget_draft.created"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["toolName"] == "draft_widget"
    assert payload["status"] == "draft"
    assert payload["requiresConfirmation"] is True
    assert payload["validation"] == {"valid": True, "warnings": [], "errors": []}
    assert payload["draft"] == {
        "status": "draft",
        "provider": "fortigate",
        "integrationId": "int_fgt_01",
        "visualType": "card",
        "title": "CPU usage",
        "fieldBindings": [
            {
                "fieldId": "system.cpu",
                "label": "CPU Usage",
                "type": "number",
                "unit": "percent",
                "source": "fortigate-system-status",
                "provider": "fortigate",
                "integrationId": "int_fgt_01",
            }
        ],
        "layout": {"w": 2, "h": 2},
        "settings": {"aggregation": "latest"},
    }
    assert payload["preview"] == {
        "source": "simulation",
        "values": {"system.cpu": 0},
    }
    assert audit["items"][0]["outcome"] == "success"
    assert audit["items"][0]["details"] == {
        "toolName": "draft_widget",
        "provider": "fortigate",
        "visualType": "card",
        "fieldCount": 1,
    }


def test_draft_widget_tool_rejects_unknown_fields_and_audits_failure():
    client = TestClient(app)

    response = client.post(
        "/api/ai/tools/draft-widget",
        headers=csrf_headers(client),
        json={
            "provider": "fortigate",
            "visualType": "bar",
            "fieldIds": ["system.missing"],
        },
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="ai.widget_draft.created"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "errors": ["Unknown provider field: system.missing"],
    }
    assert audit["items"][0]["outcome"] == "failure"
    assert audit["items"][0]["details"] == {
        "toolName": "draft_widget",
        "provider": "fortigate",
        "visualType": "bar",
        "fieldCount": 1,
        "errors": ["Unknown provider field: system.missing"],
    }
