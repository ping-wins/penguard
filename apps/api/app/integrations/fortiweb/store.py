from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.token_cipher import TokenCipher
from app.db.models import (
    FortiWebBlockRequestModel,
    FortiWebHealthCheckModel,
    FortiWebIntegrationModel,
)

FORTIWEB_CAPABILITIES = ["system", "waf_events", "ip_blocklist", "dos_response"]


def _normalize_host_for_match(host: str) -> str:
    parsed = urlparse(host if "://" in host else f"https://{host}")
    return (parsed.hostname or host).strip().lower()


def _normalize_identifier(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _device_identifiers(device: dict[str, Any] | None) -> list[str]:
    if not device:
        return []
    identifiers = {
        normalized
        for normalized in (
            _normalize_identifier(device.get("serial")),
            _normalize_identifier(device.get("serialNumber")),
            _normalize_identifier(device.get("hostname")),
        )
        if normalized
    }
    return sorted(identifiers)


class SqlAlchemyFortiWebIntegrationStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        secret_cipher: TokenCipher,
        id_factory: Callable[[], str] | None = None,
        health_id_factory: Callable[[], str] | None = None,
        block_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory is required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.secret_cipher = secret_cipher
        self.id_factory = id_factory or (lambda: f"int_fweb_{uuid4().hex[:12]}")
        self.health_id_factory = health_id_factory or (lambda: f"fweb_health_{uuid4().hex[:12]}")
        self.block_id_factory = block_id_factory or (lambda: f"fweb_block_{uuid4().hex[:12]}")

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        target_server_policy: str,
        managed_ip_list_policy: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checked_at = datetime.now(UTC)
        model = FortiWebIntegrationModel(
            id=self.id_factory(),
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            verify_tls=verify_tls,
            api_key_blob=self.secret_cipher.encrypt({"api_key": api_key}),
            status="connected",
            capabilities=FORTIWEB_CAPABILITIES,
            target_server_policy=target_server_policy,
            managed_ip_list_policy=managed_ip_list_policy,
            device_identifiers=_device_identifiers(device),
            last_checked_at=checked_at,
            created_at=checked_at,
            updated_at=checked_at,
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._created_payload(model)

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.session_factory() as db:
            rows = db.execute(
                select(FortiWebIntegrationModel)
                .where(FortiWebIntegrationModel.owner_user_id == owner_user_id)
                .order_by(FortiWebIntegrationModel.created_at)
            ).scalars()
            return {"items": [self._list_item(row) for row in rows]}

    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.get(FortiWebIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            return {
                "id": model.id,
                "host": model.host,
                "api_key": str(self.secret_cipher.decrypt(model.api_key_blob)["api_key"]),
                "verify_tls": model.verify_tls,
                "target_server_policy": model.target_server_policy,
                "managed_ip_list_policy": model.managed_ip_list_policy,
            }

    def find_public_by_host(self, source_host: str) -> dict[str, Any] | None:
        normalized_source = _normalize_host_for_match(source_host)
        with self.session_factory() as db:
            rows = db.execute(select(FortiWebIntegrationModel)).scalars()
            for row in rows:
                if _normalize_host_for_match(row.host) == normalized_source:
                    return self._list_item(row)
        return None

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        with self.session_factory() as db:
            model = db.get(FortiWebIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return False
            db.execute(
                delete(FortiWebHealthCheckModel).where(
                    FortiWebHealthCheckModel.owner_user_id == owner_user_id,
                    FortiWebHealthCheckModel.integration_id == integration_id,
                )
            )
            db.execute(
                delete(FortiWebBlockRequestModel).where(
                    FortiWebBlockRequestModel.owner_user_id == owner_user_id,
                    FortiWebBlockRequestModel.integration_id == integration_id,
                )
            )
            db.delete(model)
            db.commit()
            return True

    def record_health_check(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        ok: bool,
        status: str,
        device: dict[str, Any],
        message: str | None,
        latency_ms: int | None,
        checked_at: datetime,
    ) -> dict[str, Any]:
        checked_at = self._as_utc(checked_at)
        with self.session_factory() as db:
            integration = db.get(FortiWebIntegrationModel, integration_id)
            if integration is None or integration.owner_user_id != owner_user_id:
                raise KeyError("Integration not found")
            integration.status = status
            integration.last_checked_at = checked_at
            integration.updated_at = checked_at
            identifiers = _device_identifiers(device)
            if identifiers:
                integration.device_identifiers = identifiers
            model = FortiWebHealthCheckModel(
                id=self.health_id_factory(),
                integration_id=integration_id,
                owner_user_id=owner_user_id,
                ok=ok,
                status=status,
                device=device,
                message=message,
                latency_ms=latency_ms,
                checked_at=checked_at,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._health_check_payload(model)

    def create_block_request(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        source_ip: str,
        incident_id: str | None,
        reason: str | None,
        intent: dict[str, Any],
        preflight_summary: dict[str, Any],
        proposed_changes: list[dict[str, Any]],
        review_hash: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        model = FortiWebBlockRequestModel(
            id=self.block_id_factory(),
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            source_ip=source_ip,
            incident_id=incident_id,
            status="pending_review",
            reason=reason,
            intent_json=intent,
            preflight_summary_json=preflight_summary,
            proposed_changes_json=proposed_changes,
            review_hash=review_hash,
            created_at=now,
            updated_at=now,
        )
        with self.session_factory() as db:
            integration = db.get(FortiWebIntegrationModel, integration_id)
            if integration is None or integration.owner_user_id != owner_user_id:
                raise KeyError("Integration not found")
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._block_request_payload(model)

    def get_block_request(self, block_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.get(FortiWebBlockRequestModel, block_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            return self._block_request_payload(model)

    def list_blocks(self, *, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        with self.session_factory() as db:
            rows = db.execute(
                select(FortiWebBlockRequestModel)
                .where(
                    FortiWebBlockRequestModel.owner_user_id == owner_user_id,
                    FortiWebBlockRequestModel.integration_id == integration_id,
                )
                .order_by(FortiWebBlockRequestModel.created_at.desc())
            ).scalars()
            return {"items": [self._block_request_payload(row) for row in rows]}

    def mark_block_applied(
        self,
        *,
        block_id: str,
        owner_user_id: str,
        applied_result: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            model = db.get(FortiWebBlockRequestModel, block_id)
            if model is None or model.owner_user_id != owner_user_id:
                raise KeyError("FortiWeb block request not found")
            model.status = "active"
            model.applied_result_json = applied_result
            model.updated_at = now
            db.commit()
            db.refresh(model)
            return self._block_request_payload(model)

    def mark_block_removed(
        self,
        *,
        block_id: str,
        owner_user_id: str,
        removed_result: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            model = db.get(FortiWebBlockRequestModel, block_id)
            if model is None or model.owner_user_id != owner_user_id:
                raise KeyError("FortiWeb block request not found")
            model.status = "removed"
            model.removed_result_json = removed_result
            model.updated_at = now
            db.commit()
            db.refresh(model)
            return self._block_request_payload(model)

    def _created_payload(self, model: FortiWebIntegrationModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "type": "fortiweb",
            "name": model.name,
            "status": model.status,
            "capabilities": model.capabilities,
            "targetServerPolicy": model.target_server_policy,
            "managedIpListPolicy": model.managed_ip_list_policy,
            "lastCheckedAt": self._format_datetime(model.last_checked_at),
        }

    def _list_item(self, model: FortiWebIntegrationModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "type": "fortiweb",
            "name": model.name,
            "host": model.host,
            "status": model.status,
            "targetServerPolicy": model.target_server_policy,
            "managedIpListPolicy": model.managed_ip_list_policy,
            "lastCheckedAt": self._format_datetime(model.last_checked_at),
        }

    def _health_check_payload(self, model: FortiWebHealthCheckModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "integrationId": model.integration_id,
            "ok": model.ok,
            "status": model.status,
            "device": model.device,
            "message": model.message,
            "latencyMs": model.latency_ms,
            "checkedAt": self._format_datetime(model.checked_at),
        }

    def _block_request_payload(self, model: FortiWebBlockRequestModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "ownerUserId": model.owner_user_id,
            "integrationId": model.integration_id,
            "sourceIp": model.source_ip,
            "incidentId": model.incident_id,
            "status": model.status,
            "reason": model.reason,
            "intent": model.intent_json,
            "preflightSummary": model.preflight_summary_json,
            "proposedChanges": model.proposed_changes_json,
            "reviewHash": model.review_hash,
            "appliedResult": model.applied_result_json,
            "removedResult": model.removed_result_json,
            "createdAt": self._format_datetime(model.created_at),
            "updatedAt": self._format_datetime(model.updated_at),
        }

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
