from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.token_cipher import TokenCipher
from app.db.models import FortiGateHealthCheckModel, FortiGateIntegrationModel

FORTIGATE_CAPABILITIES = ["system", "interfaces", "policies", "threat_logs"]


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

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
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

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
