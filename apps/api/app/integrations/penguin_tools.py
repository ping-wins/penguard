from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import PenguinToolIntegrationModel
from app.soc.client import SocServiceClient

PENGUIN_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "siem_kowalski": {
        "name": "Kowalski SIEM",
        "prefix": "int_siem",
        "capabilities": ["events", "incidents", "rules", "timelines"],
    },
    "soar_skipper": {
        "name": "Skipper SOAR",
        "prefix": "int_soar",
        "capabilities": ["playbooks", "playbook_runs", "approvals", "dry_run_actions"],
    },
    "xdr_rico": {
        "name": "Rico XDR",
        "prefix": "int_xdr",
        "capabilities": ["endpoints", "endpoint_events", "heartbeats", "timelines"],
    },
}


class PenguinToolConnectionFailed(RuntimeError):
    pass


class PenguinToolClient(Protocol):
    base_url: str

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pass_through_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        pass


class PenguinToolIntegrationStore(Protocol):
    def create(
        self,
        *,
        owner_user_id: str,
        tool_type: str,
        name: str,
        host: str,
        capabilities: list[str],
        checked_at: datetime,
    ) -> dict[str, Any]:
        pass

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        pass

    def get(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any] | None:
        pass

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        pass


class PenguinToolIntegrationService:
    def __init__(
        self,
        *,
        store: PenguinToolIntegrationStore,
        clients: dict[str, PenguinToolClient],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.clients = clients
        self.clock = clock or (lambda: datetime.now(UTC))

    def test_connection(
        self, *, tool_type: str, host: str | None = None
    ) -> dict[str, Any]:
        definition = _definition(tool_type)
        client = self._resolve_client(tool_type, host=host)
        try:
            payload = client.request("GET", "/health")
        except HTTPException as exc:
            return {
                "ok": False,
                "status": "disconnected",
                "service": tool_type,
                "capabilities": definition["capabilities"],
                "error": {"message": str(exc.detail)},
            }
        status = str(payload.get("status") or "unknown")
        ok = status == "ok"
        return {
            "ok": ok,
            "status": "connected" if ok else "disconnected",
            "service": tool_type,
            "capabilities": definition["capabilities"],
            "health": payload,
        }

    def create(
        self,
        *,
        owner_user_id: str,
        tool_type: str,
        name: str | None = None,
        host: str | None = None,
    ) -> dict[str, Any]:
        result = self.test_connection(tool_type=tool_type, host=host)
        if not result["ok"]:
            message = (result.get("error") or {}).get("message") or "Penguin tool unavailable"
            raise PenguinToolConnectionFailed(message)
        definition = _definition(tool_type)
        client = self._resolve_client(tool_type, host=host)
        return self.store.create(
            owner_user_id=owner_user_id,
            tool_type=tool_type,
            name=name or str(definition["name"]),
            host=client.base_url,
            capabilities=list(definition["capabilities"]),
            checked_at=self.clock(),
        )

    def list(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        return self.store.list_public(owner_user_id=owner_user_id)

    def get(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any] | None:
        return self.store.get(integration_id=integration_id, owner_user_id=owner_user_id)

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        return self.store.delete(owner_user_id=owner_user_id, integration_id=integration_id)

    def _client(self, tool_type: str) -> PenguinToolClient:
        _definition(tool_type)
        try:
            return self.clients[tool_type]
        except KeyError as exc:
            raise ValueError(f"Missing configured client for {tool_type}") from exc

    def _resolve_client(
        self, tool_type: str, *, host: str | None
    ) -> PenguinToolClient:
        """When the wizard provides an explicit host, build an ad-hoc client
        so the user's URL is what gets probed AND persisted. Falls back to the
        env-configured client when host is missing or blank."""
        env_client = self._client(tool_type)
        candidate = (host or "").strip()
        if not candidate or candidate.rstrip("/") == env_client.base_url:
            return env_client
        return SocServiceClient(
            base_url=candidate,
            service_name=tool_type,
            timeout_seconds=env_client.timeout_seconds,
        )


class MockPenguinToolIntegrationService:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def test_connection(
        self, *, tool_type: str, host: str | None = None
    ) -> dict[str, Any]:
        definition = _definition(tool_type)
        _ = host
        return {
            "ok": True,
            "status": "connected",
            "service": tool_type,
            "capabilities": definition["capabilities"],
            "health": {"status": "ok", "service": tool_type},
        }

    def create(
        self,
        *,
        owner_user_id: str,
        tool_type: str,
        name: str | None = None,
        host: str | None = None,
    ) -> dict[str, Any]:
        definition = _definition(tool_type)
        integration_id = f"{definition['prefix']}_01"
        item = {
            "id": integration_id,
            "type": tool_type,
            "name": name or definition["name"],
            "host": (host or "").strip() or f"mock://{tool_type}",
            "status": "connected",
            "capabilities": definition["capabilities"],
            "lastCheckedAt": _format_datetime(datetime.now(UTC)),
        }
        self._items[integration_id] = item
        return item

    def list(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        return {"items": list(self._items.values())}

    def get(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any] | None:
        return self._items.get(integration_id)

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        return self._items.pop(integration_id, None) is not None


class SqlAlchemyPenguinToolIntegrationStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory is required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.id_factory = id_factory or _integration_id

    def create(
        self,
        *,
        owner_user_id: str,
        tool_type: str,
        name: str,
        host: str,
        capabilities: list[str],
        checked_at: datetime,
    ) -> dict[str, Any]:
        checked_at = checked_at.astimezone(UTC)
        model = PenguinToolIntegrationModel(
            id=self.id_factory(tool_type),
            owner_user_id=owner_user_id,
            type=tool_type,
            name=name,
            host=host,
            status="connected",
            capabilities=capabilities,
            last_checked_at=checked_at,
            created_at=checked_at,
            updated_at=checked_at,
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._payload(model)

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        _ = owner_user_id
        with self.session_factory() as db:
            rows = db.execute(
                select(PenguinToolIntegrationModel)
                .order_by(PenguinToolIntegrationModel.created_at)
            ).scalars()
            return {"items": [self._payload(row) for row in rows]}

    def get(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.get(PenguinToolIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            return self._payload(model)

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        with self.session_factory() as db:
            model = db.get(PenguinToolIntegrationModel, integration_id)
            if model is None or model.owner_user_id != owner_user_id:
                return False
            db.execute(
                delete(PenguinToolIntegrationModel).where(
                    PenguinToolIntegrationModel.id == integration_id,
                    PenguinToolIntegrationModel.owner_user_id == owner_user_id,
                )
            )
            db.commit()
            return True

    def _payload(self, model: PenguinToolIntegrationModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "type": model.type,
            "name": model.name,
            "host": model.host,
            "status": model.status,
            "capabilities": model.capabilities,
            "lastCheckedAt": _format_datetime(model.last_checked_at),
        }


def build_penguin_tool_clients(
    *,
    siem_kowalski_url: str,
    soar_skipper_url: str,
    xdr_rico_url: str,
    timeout_seconds: float,
) -> dict[str, SocServiceClient]:
    return {
        "siem_kowalski": SocServiceClient(
            base_url=siem_kowalski_url,
            service_name="siem_kowalski",
            timeout_seconds=timeout_seconds,
        ),
        "soar_skipper": SocServiceClient(
            base_url=soar_skipper_url,
            service_name="soar_skipper",
            timeout_seconds=timeout_seconds,
        ),
        "xdr_rico": SocServiceClient(
            base_url=xdr_rico_url,
            service_name="xdr_rico",
            timeout_seconds=timeout_seconds,
        ),
    }


def expected_tool_type_for_widget(widget_id: str) -> str | None:
    if widget_id in {
        "soc-incidents-by-severity",
        "soc-recent-incidents",
        "soc-top-entities",
        "soc-sla-breach",
        "soc-mttd-mttr",
    }:
        return "siem_kowalski"
    if widget_id == "xdr-endpoint-health":
        return "xdr_rico"
    if widget_id in {"soar-active-playbook-runs", "soar-playbook-run-history"}:
        return "soar_skipper"
    return None


def is_penguin_tool_type(tool_type: str) -> bool:
    return tool_type in PENGUIN_TOOL_DEFINITIONS


def _definition(tool_type: str) -> dict[str, Any]:
    try:
        return PENGUIN_TOOL_DEFINITIONS[tool_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported Penguin tool type: {tool_type}") from exc


def _integration_id(tool_type: str) -> str:
    definition = _definition(tool_type)
    return f"{definition['prefix']}_{uuid4().hex[:12]}"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
