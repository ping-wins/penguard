from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class InstalledAddonModel(Base):
    __tablename__ = "installed_addons"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass
class InstalledAddonRecord:
    id: str
    version: str
    path: str
    tag: str
    sha256: str
    status: str
    installed_at: datetime


def _to_record(model: InstalledAddonModel) -> InstalledAddonRecord:
    return InstalledAddonRecord(
        id=model.id,
        version=model.version,
        path=model.path,
        tag=model.tag,
        sha256=model.sha256,
        status=model.status,
        installed_at=model.installed_at,
    )


def upsert_installed(session: Session, record: InstalledAddonRecord) -> None:
    existing = session.get(InstalledAddonModel, record.id)
    if existing is None:
        session.add(
            InstalledAddonModel(
                id=record.id,
                version=record.version,
                path=record.path,
                tag=record.tag,
                sha256=record.sha256,
                status=record.status,
                installed_at=record.installed_at,
            )
        )
    else:
        existing.version = record.version
        existing.path = record.path
        existing.tag = record.tag
        existing.sha256 = record.sha256
        existing.status = record.status
        existing.installed_at = record.installed_at
    session.commit()


def get_installed(session: Session, addon_id: str) -> InstalledAddonRecord | None:
    model = session.get(InstalledAddonModel, addon_id)
    return _to_record(model) if model else None


def list_installed(session: Session) -> list[InstalledAddonRecord]:
    rows = session.execute(select(InstalledAddonModel)).scalars().all()
    return [_to_record(row) for row in rows]


def delete_installed(session: Session, addon_id: str) -> None:
    model = session.get(InstalledAddonModel, addon_id)
    if model is not None:
        session.delete(model)
        session.commit()
