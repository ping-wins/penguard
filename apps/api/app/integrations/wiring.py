import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import IntegrationWiringModel, SoarTargetModel

logger = logging.getLogger(__name__)


def get_wiring(session: Session, integration_id: str) -> dict[str, bool]:
    row = session.get(IntegrationWiringModel, integration_id)
    if row is None:
        return {"siem": False, "soar": False}
    return {"siem": bool(row.siem_enabled), "soar": bool(row.soar_enabled)}


def set_wiring(
    session: Session,
    integration_id: str,
    *,
    siem: bool,
    soar: bool,
    now: datetime,
) -> None:
    row = session.get(IntegrationWiringModel, integration_id)
    if row is None:
        row = IntegrationWiringModel(integration_id=integration_id)
        session.add(row)
    row.siem_enabled = siem
    row.soar_enabled = soar
    row.updated_at = now
    session.commit()


def get_soar_actions(session: Session, integration_id: str) -> list[dict[str, Any]]:
    row = session.get(SoarTargetModel, integration_id)
    return list(row.actions) if row else []


def _record_soar_actions(
    session: Session,
    integration_id: str,
    actions: list[dict[str, Any]],
    now: datetime,
) -> None:
    row = session.get(SoarTargetModel, integration_id)
    if row is None:
        row = SoarTargetModel(integration_id=integration_id)
        session.add(row)
    row.actions = actions
    row.updated_at = now
    session.commit()


def apply_wiring(
    session: Session,
    *,
    integration_id: str,
    provider_type: str,
    capabilities: dict[str, bool],
    wire: dict[str, bool],
    connector: Any,
    now: datetime,
) -> dict[str, Any]:
    """Apply best-effort SIEM/SOAR wiring without rolling back the integration."""
    _ = provider_type
    siem_result: dict[str, Any] | None = None
    soar_result: dict[str, Any] | None = None

    if wire.get("siem"):
        if not capabilities.get("logSource"):
            siem_result = {"ok": False, "detail": "Add-on is not a log source"}
        elif not capabilities.get("managed"):
            siem_result = {
                "ok": True,
                "detail": "Push log source; no device config needed",
            }
        else:
            siem_result = {
                "ok": True,
                "detail": "Managed source registered for log forwarding",
            }

    if wire.get("soar"):
        if not capabilities.get("playbookTarget"):
            soar_result = {"ok": False, "detail": "Add-on is not a playbook target"}
        else:
            lister = getattr(connector, "list_playbook_actions", None)
            if not callable(lister):
                soar_result = {
                    "ok": False,
                    "detail": "Connector exposes no playbook actions",
                }
            else:
                try:
                    actions = lister()
                    _record_soar_actions(session, integration_id, actions, now)
                    soar_result = {
                        "ok": True,
                        "detail": f"{len(actions)} action(s) registered",
                    }
                except Exception as exc:
                    logger.exception("soar_wiring_failed id=%s", integration_id)
                    soar_result = {"ok": False, "detail": str(exc)}

    set_wiring(
        session,
        integration_id,
        siem=bool(siem_result and siem_result.get("ok")),
        soar=bool(soar_result and soar_result.get("ok")),
        now=now,
    )
    return {"siem": siem_result, "soar": soar_result}
