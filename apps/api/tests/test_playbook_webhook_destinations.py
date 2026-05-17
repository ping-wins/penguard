from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import soc


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    app.dependency_overrides.clear()


def test_create_and_list_discord_destination_redacts_webhook_url():
    client = TestClient(app)

    response = client.post(
        "/api/soc/playbook-webhook-destinations",
        headers=csrf_headers(client),
        json={
            "name": "SOC Discord",
            "kind": "discord",
            "url": "https://discord.com/api/webhooks/123456789/secret-token",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "SOC Discord"
    assert body["kind"] == "discord"
    assert body["status"] == "active"
    assert body["redactedUrl"] == "https://discord.com/api/webhooks/123456789/..."
    assert "secret-token" not in str(body)
    assert "url" not in body

    list_response = client.get("/api/soc/playbook-webhook-destinations")

    assert list_response.status_code == 200
    assert list_response.json()["items"] == [body]
    assert "secret-token" not in str(list_response.json())

    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="soc.playbook.webhook_destination.created"
    )
    assert audit["items"][0]["details"] == {
        "destinationId": body["id"],
        "kind": "discord",
        "name": "SOC Discord",
        "redactedUrl": "https://discord.com/api/webhooks/123456789/...",
    }


def test_test_destination_posts_discord_payload_without_exposing_url():
    sent: list[dict] = []

    class Sender:
        def __call__(self, url: str, payload: dict, timeout_seconds: float) -> dict:
            sent.append({"url": url, "payload": payload, "timeout": timeout_seconds})
            return {"statusCode": 204, "ok": True}

    service = soc.create_playbook_webhook_destination_service(sender=Sender())
    app.dependency_overrides[soc.get_playbook_webhook_destination_service] = lambda: service
    client = TestClient(app)

    created = client.post(
        "/api/soc/playbook-webhook-destinations",
        headers=csrf_headers(client),
        json={
            "name": "SOC Discord",
            "kind": "discord",
            "url": "https://discord.com/api/webhooks/123456789/secret-token",
        },
    ).json()

    response = client.post(
        f"/api/soc/playbook-webhook-destinations/{created['id']}/test",
        headers=csrf_headers(client),
        json={"content": "FortiDashboard test"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "destinationId": created["id"],
        "statusCode": 204,
        "ok": True,
    }
    assert sent == [
        {
            "url": "https://discord.com/api/webhooks/123456789/secret-token",
            "payload": {"content": "FortiDashboard test"},
            "timeout": 5.0,
        }
    ]
    assert "secret-token" not in str(response.json())
