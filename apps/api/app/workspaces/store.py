from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import WorkspaceSpecModel


class SqlAlchemyWorkspaceStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory is required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.clock = clock or (lambda: datetime.now(UTC))

    def get(self, workspace_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceSpecModel).where(
                    WorkspaceSpecModel.workspace_id == workspace_id,
                    WorkspaceSpecModel.owner_user_id == owner_user_id,
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            return self._workspace_payload(model)

    def save(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        name: str,
        widgets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = self.clock().astimezone(UTC)
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceSpecModel).where(
                    WorkspaceSpecModel.workspace_id == workspace_id,
                    WorkspaceSpecModel.owner_user_id == owner_user_id,
                )
            ).scalar_one_or_none()
            if model is None:
                model = WorkspaceSpecModel(
                    workspace_id=workspace_id,
                    owner_user_id=owner_user_id,
                    name=name,
                    widgets=widgets,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(model)
            else:
                model.name = name
                model.widgets = widgets
                model.version += 1
                model.updated_at = now
            db.commit()
            db.refresh(model)
            return {
                "id": model.workspace_id,
                "version": model.version,
                "updatedAt": self._format_datetime(model.updated_at),
            }

    def _workspace_payload(self, model: WorkspaceSpecModel) -> dict[str, Any]:
        return {
            "id": model.workspace_id,
            "name": model.name,
            "widgets": model.widgets,
            "version": model.version,
            "updatedAt": self._format_datetime(model.updated_at),
        }

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
