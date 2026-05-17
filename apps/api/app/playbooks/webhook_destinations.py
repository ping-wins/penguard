from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth.token_cipher import TokenCipher
from app.db.models import PlaybookWebhookDestinationModel

WebhookSender = Callable[[str, dict[str, Any], float], dict[str, Any]]


class PlaybookWebhookDestinationStore(Protocol):
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        kind: str,
        url: str,
    ) -> dict[str, Any]:
        pass

    def list(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        pass

    def get_url(self, *, owner_user_id: str, destination_id: str) -> str:
        pass

    def get_public(self, *, owner_user_id: str, destination_id: str) -> dict[str, Any]:
        pass


class InMemoryPlaybookWebhookDestinationStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._urls: dict[str, str] = {}

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        kind: str,
        url: str,
    ) -> dict[str, Any]:
        item = _public_item(
            destination_id=_destination_id(),
            owner_user_id=owner_user_id,
            name=name,
            kind=kind,
            redacted_url=redact_webhook_url(url),
            status="active",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._items[item["id"]] = item
        self._urls[item["id"]] = url
        return dict(item)

    def list(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self._items.values()
            if item["ownerUserId"] == owner_user_id
        ]

    def get_url(self, *, owner_user_id: str, destination_id: str) -> str:
        item = self.get_public(owner_user_id=owner_user_id, destination_id=destination_id)
        _ = item
        return self._urls[destination_id]

    def get_public(self, *, owner_user_id: str, destination_id: str) -> dict[str, Any]:
        item = self._items.get(destination_id)
        if item is None or item["ownerUserId"] != owner_user_id:
            raise KeyError("Webhook destination not found")
        return dict(item)


class SqlAlchemyPlaybookWebhookDestinationStore:
    def __init__(self, *, database_url: str, token_cipher: TokenCipher) -> None:
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.token_cipher = token_cipher

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        kind: str,
        url: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        model = PlaybookWebhookDestinationModel(
            id=_destination_id(),
            owner_user_id=owner_user_id,
            name=name,
            kind=kind,
            url_blob=self.token_cipher.encrypt({"url": url}),
            redacted_url=redact_webhook_url(url),
            status="active",
            created_at=now,
            updated_at=now,
        )
        with self.SessionLocal() as db:
            db.add(model)
            db.commit()
            db.refresh(model)
            return _model_public_item(model)

    def list(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            rows = db.scalars(
                select(PlaybookWebhookDestinationModel)
                .where(PlaybookWebhookDestinationModel.owner_user_id == owner_user_id)
                .order_by(PlaybookWebhookDestinationModel.created_at.asc())
            ).all()
            return [_model_public_item(row) for row in rows]

    def get_url(self, *, owner_user_id: str, destination_id: str) -> str:
        model = self._get(owner_user_id=owner_user_id, destination_id=destination_id)
        payload = self.token_cipher.decrypt(model.url_blob)
        url = payload.get("url")
        if not isinstance(url, str) or not url:
            raise KeyError("Webhook destination URL is unavailable")
        return url

    def get_public(self, *, owner_user_id: str, destination_id: str) -> dict[str, Any]:
        return _model_public_item(
            self._get(owner_user_id=owner_user_id, destination_id=destination_id)
        )

    def _get(self, *, owner_user_id: str, destination_id: str) -> PlaybookWebhookDestinationModel:
        with self.SessionLocal() as db:
            model = db.get(PlaybookWebhookDestinationModel, destination_id)
            if model is None or model.owner_user_id != owner_user_id:
                raise KeyError("Webhook destination not found")
            return model


class PlaybookWebhookDestinationService:
    def __init__(
        self,
        *,
        store: PlaybookWebhookDestinationStore,
        sender: WebhookSender | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.store = store
        self.sender = sender or send_webhook
        self.timeout_seconds = timeout_seconds

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        kind: str,
        url: str,
    ) -> dict[str, Any]:
        normalized_kind = kind.strip().lower()
        if normalized_kind not in {"discord", "generic"}:
            raise ValueError("Unsupported webhook destination kind")
        validate_webhook_url(url, kind=normalized_kind)
        return self.store.create(
            owner_user_id=owner_user_id,
            name=name.strip(),
            kind=normalized_kind,
            url=url.strip(),
        )

    def list(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        return self.store.list(owner_user_id=owner_user_id)

    def send(
        self,
        *,
        owner_user_id: str,
        destination_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = self.store.get_url(owner_user_id=owner_user_id, destination_id=destination_id)
        result = self.sender(url, payload, self.timeout_seconds)
        return {
            "destinationId": destination_id,
            "statusCode": int(result.get("statusCode") or 0),
            "ok": bool(result.get("ok")),
        }

    def public_item(self, *, owner_user_id: str, destination_id: str) -> dict[str, Any]:
        return self.store.get_public(owner_user_id=owner_user_id, destination_id=destination_id)


def send_webhook(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    response = httpx.post(url, json=payload, timeout=timeout_seconds)
    return {"statusCode": response.status_code, "ok": response.is_success}


def validate_webhook_url(url: str, *, kind: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Webhook URL must be an HTTPS URL")
    if kind == "discord" and parsed.netloc not in {
        "discord.com",
        "discordapp.com",
        "ptb.discord.com",
        "canary.discord.com",
    }:
        raise ValueError("Discord webhook URL must point to discord.com")
    if kind == "discord" and not parsed.path.startswith("/api/webhooks/"):
        raise ValueError("Discord webhook URL must use /api/webhooks/")


def redact_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) >= 3 and segments[0] == "api" and segments[1] == "webhooks":
        return f"{parsed.scheme}://{parsed.netloc}/api/webhooks/{segments[2]}/..."
    return f"{parsed.scheme}://{parsed.netloc}/..."


def _destination_id() -> str:
    return f"pwd_{token_urlsafe(12)}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _public_item(
    *,
    destination_id: str,
    owner_user_id: str,
    name: str,
    kind: str,
    redacted_url: str,
    status: str,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "id": destination_id,
        "ownerUserId": owner_user_id,
        "name": name,
        "kind": kind,
        "redactedUrl": redacted_url,
        "status": status,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _model_public_item(model: PlaybookWebhookDestinationModel) -> dict[str, Any]:
    return _public_item(
        destination_id=model.id,
        owner_user_id=model.owner_user_id,
        name=model.name,
        kind=model.kind,
        redacted_url=model.redacted_url,
        status=model.status,
        created_at=model.created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        updated_at=model.updated_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )
