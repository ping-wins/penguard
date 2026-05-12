from collections.abc import Callable
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import Engine, create_engine, desc, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import WorkspaceSpecModel, WorkspaceTemplateModel


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
        presentation: dict[str, Any] | None = None,
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
                    presentation=presentation,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(model)
            else:
                model.name = name
                model.widgets = widgets
                if presentation is not None:
                    model.presentation = presentation
                model.version += 1
                model.updated_at = now
            db.commit()
            db.refresh(model)
            return {
                "id": model.workspace_id,
                "version": model.version,
                "updatedAt": self._format_datetime(model.updated_at),
            }

    def rebind_widget_integration(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        instance_id: str,
        integration_id: str,
    ) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceSpecModel).where(
                    WorkspaceSpecModel.workspace_id == workspace_id,
                    WorkspaceSpecModel.owner_user_id == owner_user_id,
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            widgets = list(model.widgets or [])
            matched = False
            for index, widget in enumerate(widgets):
                if not isinstance(widget, dict) or widget.get("instanceId") != instance_id:
                    continue
                updated = dict(widget)
                updated["integrationId"] = integration_id
                bindings = updated.get("fieldBindings")
                if isinstance(bindings, list) and bindings:
                    updated["fieldBindings"] = [
                        {**binding, "integrationId": integration_id}
                        if isinstance(binding, dict)
                        else binding
                        for binding in bindings
                    ]
                widgets[index] = updated
                matched = True
                break
            if not matched:
                return None
            model.widgets = widgets
            model.updated_at = self.clock().astimezone(UTC)
            model.version += 1
            origin = model.origin
            if isinstance(origin, dict) and origin.get("missingProviderTypes"):
                origin = {**origin, "missingProviderTypes": []}
                model.origin = origin
            db.commit()
            db.refresh(model)
            return self._workspace_payload(model)

    def set_presentation(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        presentation: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceSpecModel).where(
                    WorkspaceSpecModel.workspace_id == workspace_id,
                    WorkspaceSpecModel.owner_user_id == owner_user_id,
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            model.presentation = presentation
            model.updated_at = self.clock().astimezone(UTC)
            db.commit()
            db.refresh(model)
            return self._workspace_payload(model)

    def create_workspace_from_manifest(
        self,
        *,
        owner_user_id: str,
        workspace_id: str,
        name: str,
        widgets: list[dict[str, Any]],
        presentation: dict[str, Any] | None,
        origin: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self.clock().astimezone(UTC)
        with self.session_factory() as db:
            model = WorkspaceSpecModel(
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                name=name,
                widgets=widgets,
                presentation=presentation,
                origin=origin,
                version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._workspace_payload(model)

    def list_workspaces(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = (
                db.execute(
                    select(WorkspaceSpecModel)
                    .where(WorkspaceSpecModel.owner_user_id == owner_user_id)
                    .order_by(desc(WorkspaceSpecModel.updated_at))
                )
                .scalars()
                .all()
            )
            return [self._workspace_summary(row) for row in rows]

    def delete_workspace(self, *, workspace_id: str, owner_user_id: str) -> bool:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceSpecModel).where(
                    WorkspaceSpecModel.workspace_id == workspace_id,
                    WorkspaceSpecModel.owner_user_id == owner_user_id,
                )
            ).scalar_one_or_none()
            if model is None:
                return False
            db.delete(model)
            db.commit()
            return True

    def publish_template(
        self,
        *,
        slug: str,
        title: str,
        description: str | None,
        tags: list[str],
        manifest: dict[str, Any],
        published_by_user_id: str,
        published_by_email: str | None,
    ) -> dict[str, Any]:
        now = self.clock().astimezone(UTC)
        with self.session_factory() as db:
            existing = db.execute(
                select(WorkspaceTemplateModel).where(WorkspaceTemplateModel.slug == slug)
            ).scalar_one_or_none()
            if existing is not None:
                if existing.published_by_user_id != published_by_user_id:
                    raise PermissionError("Template slug already owned by another user")
                existing.title = title
                existing.description = description
                existing.tags = tags
                existing.manifest = manifest
                existing.published_by_email = published_by_email
                existing.is_visible = True
                existing.updated_at = now
                model = existing
            else:
                model = WorkspaceTemplateModel(
                    id=f"wstpl_{token_urlsafe(9)}",
                    slug=slug,
                    title=title,
                    description=description,
                    tags=tags,
                    manifest=manifest,
                    published_by_user_id=published_by_user_id,
                    published_by_email=published_by_email,
                    install_count=0,
                    is_visible=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(model)
            db.commit()
            db.refresh(model)
            return self._template_payload(model, include_manifest=True)

    def list_templates(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = (
                db.execute(
                    select(WorkspaceTemplateModel)
                    .where(WorkspaceTemplateModel.is_visible == True)  # noqa: E712
                    .order_by(desc(WorkspaceTemplateModel.created_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [self._template_payload(row, include_manifest=False) for row in rows]

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceTemplateModel).where(WorkspaceTemplateModel.id == template_id)
            ).scalar_one_or_none()
            if model is None:
                return None
            return self._template_payload(model, include_manifest=True)

    def delete_template(self, *, template_id: str, published_by_user_id: str) -> bool:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceTemplateModel).where(WorkspaceTemplateModel.id == template_id)
            ).scalar_one_or_none()
            if model is None:
                return False
            if model.published_by_user_id != published_by_user_id:
                raise PermissionError("Template not owned by user")
            db.delete(model)
            db.commit()
            return True

    def increment_template_install(self, template_id: str) -> None:
        with self.session_factory() as db:
            model = db.execute(
                select(WorkspaceTemplateModel).where(WorkspaceTemplateModel.id == template_id)
            ).scalar_one_or_none()
            if model is None:
                return
            model.install_count += 1
            db.commit()

    def _workspace_payload(self, model: WorkspaceSpecModel) -> dict[str, Any]:
        return {
            "id": model.workspace_id,
            "name": model.name,
            "widgets": model.widgets,
            "presentation": model.presentation,
            "origin": model.origin,
            "version": model.version,
            "updatedAt": self._format_datetime(model.updated_at),
        }

    def _workspace_summary(self, model: WorkspaceSpecModel) -> dict[str, Any]:
        widgets = model.widgets or []
        return {
            "id": model.workspace_id,
            "name": model.name,
            "widgetCount": len(widgets) if isinstance(widgets, list) else 0,
            "version": model.version,
            "origin": model.origin,
            "hasPresentation": bool(model.presentation),
            "createdAt": self._format_datetime(model.created_at),
            "updatedAt": self._format_datetime(model.updated_at),
        }

    def _template_payload(
        self,
        model: WorkspaceTemplateModel,
        *,
        include_manifest: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": model.id,
            "slug": model.slug,
            "title": model.title,
            "description": model.description,
            "tags": model.tags,
            "publishedByEmail": model.published_by_email,
            "publishedByUserId": model.published_by_user_id,
            "installCount": model.install_count,
            "createdAt": self._format_datetime(model.created_at),
            "updatedAt": self._format_datetime(model.updated_at),
        }
        if include_manifest:
            payload["manifest"] = model.manifest
        return payload

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
