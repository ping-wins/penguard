from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.token_cipher import TokenCipher
from app.db.models import (
    FortiGateHealthCheckModel,
    FortiGateIngestionStatusModel,
    FortiGateIntegrationModel,
)

FORTIGATE_CAPABILITIES = ["system", "interfaces", "policies", "threat_logs"]


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


def _syslog_identifier_candidates(fields: dict[str, str]) -> set[str]:
    return {
        normalized
        for normalized in (
            _normalize_identifier(fields.get("devid")),
            _normalize_identifier(fields.get("devname")),
            _normalize_identifier(fields.get("serial")),
            _normalize_identifier(fields.get("integrationid")),
        )
        if normalized
    }


class SqlAlchemyFortiGateIntegrationStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        secret_cipher: TokenCipher,
        id_factory: Callable[[], str] | None = None,
        health_id_factory: Callable[[], str] | None = None,
        ingestion_id_factory: Callable[[], str] | None = None,
        default_ingestion_interval_seconds: int = 60,
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
        self.id_factory = id_factory or (lambda: f"int_fgt_{uuid4().hex[:12]}")
        self.health_id_factory = health_id_factory or (lambda: f"fgt_health_{uuid4().hex[:12]}")
        self.ingestion_id_factory = ingestion_id_factory or (
            lambda: f"fgt_ingest_{uuid4().hex[:12]}"
        )
        self.default_ingestion_interval_seconds = default_ingestion_interval_seconds

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checked_at = datetime.now(UTC)
        model = FortiGateIntegrationModel(
            id=self.id_factory(),
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            verify_tls=verify_tls,
            api_key_blob=self.secret_cipher.encrypt({"api_key": api_key}),
            status="connected",
            capabilities=FORTIGATE_CAPABILITIES,
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
                select(FortiGateIntegrationModel)
                .where(FortiGateIntegrationModel.owner_user_id == owner_user_id)
                .order_by(FortiGateIntegrationModel.created_at)
            ).scalars()
            return {"items": [self._list_item(row) for row in rows]}

    def get_api_key(self, integration_id: str, *, owner_user_id: str) -> str | None:
        with self.session_factory() as db:
            model = db.get(FortiGateIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            return str(self.secret_cipher.decrypt(model.api_key_blob)["api_key"])

    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.get(FortiGateIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            return {
                "id": model.id,
                "host": model.host,
                "api_key": str(self.secret_cipher.decrypt(model.api_key_blob)["api_key"]),
                "verify_tls": model.verify_tls,
            }

    def find_public_by_host(self, source_host: str) -> dict[str, Any] | None:
        normalized_source = _normalize_host_for_match(source_host)
        with self.session_factory() as db:
            rows = db.execute(select(FortiGateIntegrationModel)).scalars()
            for row in rows:
                if _normalize_host_for_match(row.host) == normalized_source:
                    return self._list_item(row)
        return None

    def find_syslog_source(
        self,
        source_host: str,
        fields: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        normalized_source = _normalize_host_for_match(source_host)
        candidates = _syslog_identifier_candidates(fields or {})
        with self.session_factory() as db:
            rows = list(db.execute(select(FortiGateIntegrationModel)).scalars())
            if candidates:
                for row in rows:
                    identifiers = set(row.device_identifiers or [])
                    if identifiers.intersection(candidates):
                        return {"integrationId": row.id, "ownerUserId": row.owner_user_id}
            for row in rows:
                if _normalize_host_for_match(row.host) == normalized_source:
                    return {"integrationId": row.id, "ownerUserId": row.owner_user_id}
        return None

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        with self.session_factory() as db:
            model = db.get(FortiGateIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return False
            db.execute(
                delete(FortiGateHealthCheckModel).where(
                    FortiGateHealthCheckModel.owner_user_id == owner_user_id,
                    FortiGateHealthCheckModel.integration_id == integration_id,
                )
            )
            db.execute(
                delete(FortiGateIngestionStatusModel).where(
                    FortiGateIngestionStatusModel.owner_user_id == owner_user_id,
                    FortiGateIngestionStatusModel.integration_id == integration_id,
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
        checked_at = checked_at.astimezone(UTC)
        with self.session_factory() as db:
            integration = db.get(FortiGateIntegrationModel, integration_id)
            if integration is None or integration.owner_user_id != owner_user_id:
                raise KeyError("Integration not found")
            integration.status = status
            integration.last_checked_at = checked_at
            integration.updated_at = checked_at
            identifiers = _device_identifiers(device)
            if identifiers:
                integration.device_identifiers = identifiers
            model = FortiGateHealthCheckModel(
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

    def list_health_checks(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        limit: int = 20,
    ) -> dict[str, list[dict[str, Any]]]:
        with self.session_factory() as db:
            integration = db.get(FortiGateIntegrationModel, integration_id)
            if integration is None or integration.owner_user_id != owner_user_id:
                raise KeyError("Integration not found")
            rows = db.execute(
                select(FortiGateHealthCheckModel)
                .where(
                    FortiGateHealthCheckModel.owner_user_id == owner_user_id,
                    FortiGateHealthCheckModel.integration_id == integration_id,
                )
                .order_by(FortiGateHealthCheckModel.checked_at.desc())
                .limit(limit)
            ).scalars()
            return {"items": [self._health_check_payload(row) for row in rows]}

    def get_ingestion_status(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=datetime.now(UTC),
            )
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def upsert_ingestion_status(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        enabled: bool,
        interval_seconds: int,
        updated_at: datetime,
    ) -> dict[str, Any]:
        updated_at = self._as_utc(updated_at)
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=updated_at,
            )
            model.enabled = enabled
            model.interval_seconds = interval_seconds
            if model.status == "running":
                model.status = "idle"
            model.updated_at = updated_at
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def record_ingestion_started(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        started_at: datetime,
        trigger: str,
    ) -> dict[str, Any]:
        started_at = self._as_utc(started_at)
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=started_at,
            )
            model.status = "running"
            model.last_started_at = started_at
            model.last_run_trigger = trigger
            model.last_error = None
            model.updated_at = started_at
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def record_ingestion_result(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        ok: bool,
        raw_event_count: int,
        created_count: int,
        event_ids: list[str],
        error: str | None,
        finished_at: datetime,
    ) -> dict[str, Any]:
        finished_at = self._as_utc(finished_at)
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=finished_at,
            )
            model.status = "success" if ok else "failed"
            model.last_finished_at = finished_at
            model.last_raw_event_count = raw_event_count
            model.last_created_count = created_count
            model.last_event_ids = event_ids
            model.last_error = error
            if ok:
                model.last_success_at = finished_at
            model.updated_at = finished_at
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def mark_syslog_forwarding_configured(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        configured_at: datetime,
    ) -> dict[str, Any]:
        configured_at = self._as_utc(configured_at)
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=configured_at,
            )
            model.enabled = False
            model.status = "waiting_syslog"
            model.last_error = None
            model.last_run_trigger = "syslog"
            model.updated_at = configured_at
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def record_syslog_event(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        received_at: datetime,
    ) -> dict[str, Any]:
        received_at = self._as_utc(received_at)
        with self.session_factory() as db:
            integration = self._owned_integration(
                db,
                owner_user_id=owner_user_id,
                integration_id=integration_id,
            )
            model = self._get_or_create_ingestion_status(
                db,
                integration=integration,
                now=received_at,
            )
            event_ids = list(model.last_event_ids or [])
            if event_id:
                event_ids.append(event_id)
            model.enabled = False
            model.status = "streaming"
            model.last_finished_at = received_at
            model.last_success_at = received_at
            model.last_raw_event_count = int(model.last_raw_event_count or 0) + 1
            model.last_created_count = int(model.last_created_count or 0) + 1
            model.last_event_ids = event_ids[-20:]
            model.last_error = None
            model.last_run_trigger = "syslog"
            model.updated_at = received_at
            db.commit()
            db.refresh(model)
            return self._ingestion_status_payload(model)

    def reset_ingestion_cursors(self) -> None:
        with self.session_factory() as db:
            db.execute(
                FortiGateIngestionStatusModel.__table__.update().values(
                    last_started_at=None,
                    last_finished_at=None,
                    last_success_at=None,
                    last_error=None,
                    last_raw_event_count=0,
                    last_created_count=0,
                    last_event_ids=[],
                    last_run_trigger=None,
                    status="idle",
                )
            )
            db.commit()

    def list_due_ingestion_statuses(
        self,
        *,
        now: datetime,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        now = self._as_utc(now)
        with self.session_factory() as db:
            rows = db.execute(
                select(FortiGateIngestionStatusModel)
                .where(
                    FortiGateIngestionStatusModel.enabled.is_(True),
                    FortiGateIngestionStatusModel.status != "running",
                )
                .order_by(FortiGateIngestionStatusModel.updated_at)
                .limit(limit)
            ).scalars()
            due: list[dict[str, Any]] = []
            for row in rows:
                last_finished = row.last_finished_at or row.last_started_at
                if last_finished is None:
                    due.append(self._ingestion_status_payload(row, include_owner=True))
                    continue
                last_finished = self._as_utc(last_finished)
                if last_finished + timedelta(seconds=row.interval_seconds) <= now:
                    due.append(self._ingestion_status_payload(row, include_owner=True))
            return due

    def _created_payload(self, model: FortiGateIntegrationModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "type": "fortigate",
            "name": model.name,
            "status": model.status,
            "capabilities": model.capabilities,
            "lastCheckedAt": self._format_datetime(model.last_checked_at),
        }

    def _list_item(self, model: FortiGateIntegrationModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "type": "fortigate",
            "name": model.name,
            "host": model.host,
            "status": model.status,
            "lastCheckedAt": self._format_datetime(model.last_checked_at),
        }

    def _health_check_payload(self, model: FortiGateHealthCheckModel) -> dict[str, Any]:
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

    def _owned_integration(
        self,
        db: Session,
        *,
        owner_user_id: str,
        integration_id: str,
    ) -> FortiGateIntegrationModel:
        integration = db.get(FortiGateIntegrationModel, integration_id)
        if integration is None or integration.owner_user_id != owner_user_id:
            raise KeyError("Integration not found")
        return integration

    def _get_or_create_ingestion_status(
        self,
        db: Session,
        *,
        integration: FortiGateIntegrationModel,
        now: datetime,
    ) -> FortiGateIngestionStatusModel:
        model = db.execute(
            select(FortiGateIngestionStatusModel).where(
                FortiGateIngestionStatusModel.owner_user_id == integration.owner_user_id,
                FortiGateIngestionStatusModel.integration_id == integration.id,
            )
        ).scalar_one_or_none()
        if model is not None:
            return model
        model = FortiGateIngestionStatusModel(
            id=self.ingestion_id_factory(),
            integration_id=integration.id,
            owner_user_id=integration.owner_user_id,
            enabled=False,
            interval_seconds=self.default_ingestion_interval_seconds,
            status="idle",
            last_raw_event_count=0,
            last_created_count=0,
            last_event_ids=[],
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        db.flush()
        return model

    def _ingestion_status_payload(
        self,
        model: FortiGateIngestionStatusModel,
        *,
        include_owner: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "id": model.id,
            "integrationId": model.integration_id,
            "enabled": model.enabled,
            "intervalSeconds": model.interval_seconds,
            "status": model.status,
            "lastStartedAt": self._format_optional_datetime(model.last_started_at),
            "lastFinishedAt": self._format_optional_datetime(model.last_finished_at),
            "lastSuccessAt": self._format_optional_datetime(model.last_success_at),
            "lastError": model.last_error,
            "lastRawEventCount": model.last_raw_event_count,
            "lastCreatedCount": model.last_created_count,
            "lastEventIds": model.last_event_ids or [],
            "lastRunTrigger": model.last_run_trigger,
            "updatedAt": self._format_datetime(model.updated_at),
        }
        if include_owner:
            payload["ownerUserId"] = model.owner_user_id
        return payload

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _format_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self._format_datetime(value)

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class InMemoryFortiGateIngestionStore:
    def __init__(
        self,
        *,
        default_ingestion_interval_seconds: int = 60,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.default_ingestion_interval_seconds = default_ingestion_interval_seconds
        self.id_factory = id_factory or (lambda: f"fgt_ingest_{uuid4().hex[:12]}")
        self._statuses: dict[tuple[str, str], dict[str, Any]] = {}

    def get_ingestion_status(self, *, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        return dict(self._get_or_create(owner_user_id, integration_id))

    def upsert_ingestion_status(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        enabled: bool,
        interval_seconds: int,
        updated_at: datetime,
    ) -> dict[str, Any]:
        status = self._get_or_create(owner_user_id, integration_id)
        status["enabled"] = enabled
        status["intervalSeconds"] = interval_seconds
        if status["status"] == "running":
            status["status"] = "idle"
        status["updatedAt"] = self._format_datetime(updated_at)
        return dict(status)

    def record_ingestion_started(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        started_at: datetime,
        trigger: str,
    ) -> dict[str, Any]:
        status = self._get_or_create(owner_user_id, integration_id)
        formatted = self._format_datetime(started_at)
        status["status"] = "running"
        status["lastStartedAt"] = formatted
        status["lastRunTrigger"] = trigger
        status["lastError"] = None
        status["updatedAt"] = formatted
        return dict(status)

    def record_ingestion_result(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        ok: bool,
        raw_event_count: int,
        created_count: int,
        event_ids: list[str],
        error: str | None,
        finished_at: datetime,
    ) -> dict[str, Any]:
        status = self._get_or_create(owner_user_id, integration_id)
        formatted = self._format_datetime(finished_at)
        status["status"] = "success" if ok else "failed"
        status["lastFinishedAt"] = formatted
        status["lastRawEventCount"] = raw_event_count
        status["lastCreatedCount"] = created_count
        status["lastEventIds"] = event_ids
        status["lastError"] = error
        if ok:
            status["lastSuccessAt"] = formatted
        status["updatedAt"] = formatted
        return dict(status)

    def mark_syslog_forwarding_configured(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        configured_at: datetime,
    ) -> dict[str, Any]:
        status = self._get_or_create(owner_user_id, integration_id)
        formatted = self._format_datetime(configured_at)
        status["enabled"] = False
        status["status"] = "waiting_syslog"
        status["lastError"] = None
        status["lastRunTrigger"] = "syslog"
        status["updatedAt"] = formatted
        return dict(status)

    def record_syslog_event(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        received_at: datetime,
    ) -> dict[str, Any]:
        status = self._get_or_create(owner_user_id, integration_id)
        formatted = self._format_datetime(received_at)
        event_ids = list(status["lastEventIds"])
        if event_id:
            event_ids.append(event_id)
        status["enabled"] = False
        status["status"] = "streaming"
        status["lastFinishedAt"] = formatted
        status["lastSuccessAt"] = formatted
        status["lastRawEventCount"] += 1
        status["lastCreatedCount"] += 1
        status["lastEventIds"] = event_ids[-20:]
        status["lastError"] = None
        status["lastRunTrigger"] = "syslog"
        status["updatedAt"] = formatted
        return dict(status)

    def list_due_ingestion_statuses(
        self,
        *,
        now: datetime,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        now = self._as_utc(now)
        due: list[dict[str, Any]] = []
        for (owner_user_id, _integration_id), status in self._statuses.items():
            if not status["enabled"] or status["status"] == "running":
                continue
            last_finished_raw = status["lastFinishedAt"] or status["lastStartedAt"]
            if last_finished_raw is not None:
                last_finished = datetime.fromisoformat(last_finished_raw.replace("Z", "+00:00"))
                if last_finished + timedelta(seconds=status["intervalSeconds"]) > now:
                    continue
            due_status = dict(status)
            due_status["ownerUserId"] = owner_user_id
            due.append(due_status)
            if len(due) >= limit:
                break
        return due

    def reset_ingestion_cursors(self) -> None:
        for status in self._statuses.values():
            status["status"] = "idle"
            status["lastStartedAt"] = None
            status["lastFinishedAt"] = None
            status["lastSuccessAt"] = None
            status["lastError"] = None
            status["lastRawEventCount"] = 0
            status["lastCreatedCount"] = 0
            status["lastEventIds"] = []
            status["lastRunTrigger"] = None

    def _get_or_create(self, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        key = (owner_user_id, integration_id)
        status = self._statuses.get(key)
        if status is not None:
            return status
        now = self._format_datetime(datetime.now(UTC))
        status = {
            "id": self.id_factory(),
            "integrationId": integration_id,
            "enabled": False,
            "intervalSeconds": self.default_ingestion_interval_seconds,
            "status": "idle",
            "lastStartedAt": None,
            "lastFinishedAt": None,
            "lastSuccessAt": None,
            "lastError": None,
            "lastRawEventCount": 0,
            "lastCreatedCount": 0,
            "lastEventIds": [],
            "lastRunTrigger": None,
            "updatedAt": now,
        }
        self._statuses[key] = status
        return status

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _format_datetime(self, value: datetime) -> str:
        value = self._as_utc(value)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
