import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.addons.bootstrap import bootstrap_installed_addons
from app.addons.dependencies import get_connector_registry, get_loader
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.fortigate.syslog import (
    FortiGateSyslogForwarder,
    start_fortigate_syslog_udp_collector,
)
from app.realtime import realtime_broker
from app.routers import (
    ai,
    audit,
    auth,
    health,
    integrations,
    lab_demo,
    marketplace,
    providers,
    realtime,
    soc,
    soc_ingest,
    widget_catalog,
    widgets,
    workspaces,
)

logger = logging.getLogger(__name__)
_settings = get_settings()
_FORTIGATE_REALTIME_WIDGET_IDS = ("fortigate-system-status",)
_fortigate_realtime_widget_last_sent: dict[tuple[str, str], datetime] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        with SessionLocal() as session:
            bootstrap_installed_addons(
                session=session,
                loader=get_loader(),
                registry=get_connector_registry(),
            )
    except Exception:
        logger.exception("addon_bootstrap_unhandled")

    scheduler_task: asyncio.Task | None = None
    syslog_transport: asyncio.DatagramTransport | None = None
    if _settings.fortigate_ingestion_scheduler_enabled:
        scheduler_task = asyncio.create_task(_fortigate_ingestion_scheduler_loop())
    syslog_transport = await _start_fortigate_syslog_collector()
    try:
        yield
    finally:
        if syslog_transport is not None:
            syslog_transport.close()
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


async def _fortigate_ingestion_scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(integrations.run_due_fortigate_ingestions_once)
        except Exception:
            logger.exception("fortigate_ingestion_scheduler_tick_failed")
        await asyncio.sleep(_settings.fortigate_ingestion_scheduler_tick_seconds)


def _fortigate_realtime_widget_snapshots(
    *,
    widget_service: Any,
    owner_user_id: str,
    integration_id: str,
    now: datetime,
    last_sent: dict[tuple[str, str], datetime] | None = None,
    min_interval_seconds: int = 2,
) -> list[dict[str, Any]]:
    sent_at = last_sent if last_sent is not None else _fortigate_realtime_widget_last_sent
    throttle_key = (owner_user_id, integration_id)
    previous_sent_at = sent_at.get(throttle_key)
    if (
        previous_sent_at is not None
        and (now - previous_sent_at).total_seconds() < min_interval_seconds
    ):
        return []

    snapshots: list[dict[str, Any]] = []
    for widget_id in _FORTIGATE_REALTIME_WIDGET_IDS:
        try:
            snapshot = widget_service.get_widget_data(
                widget_id,
                integration_id,
                owner_user_id=owner_user_id,
            )
        except Exception:
            logger.exception(
                "fortigate_realtime_widget_snapshot_failed widget_id=%s integration_id=%s",
                widget_id,
                integration_id,
            )
            continue
        snapshots.append(snapshot)

    if snapshots:
        sent_at[throttle_key] = now
    return snapshots


async def _start_fortigate_syslog_collector() -> asyncio.DatagramTransport:
    fortigate_service = integrations.get_fortigate_integration_service()
    fortigate_widget_service = widgets.get_fortigate_widget_service()

    def resolve(addr, _fields):
        if addr is None:
            return None
        return fortigate_service.resolve_syslog_integration_id(
            source_host=addr[0],
            fields=_fields,
        )

    def record_status(
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        ticket: dict | None = None,
    ) -> None:
        received_at = datetime.now(UTC)
        fortigate_service.record_syslog_event(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            event_id=event_id,
            received_at=received_at,
        )
        widget_snapshots = _fortigate_realtime_widget_snapshots(
            widget_service=fortigate_widget_service,
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            now=received_at,
        )
        realtime_broker.publish(
            {
                "type": "fortigate.syslog.event",
                "ownerUserId": owner_user_id,
                "integrationId": integration_id,
                "eventId": event_id,
                "receivedAt": received_at.isoformat(timespec="milliseconds").replace(
                    "+00:00",
                    "Z",
                ),
                "ticket": ticket,
                "widgets": widget_snapshots,
            }
        )

    forwarder = FortiGateSyslogForwarder(
        siem_client=soc.get_siem_client(),
        integration_resolver=resolve,
        status_recorder=record_status,
    )
    return await start_fortigate_syslog_udp_collector(
        host=_settings.fortigate_syslog_collector_host,
        port=_settings.fortigate_syslog_collector_port,
        forwarder=forwarder,
    )


app = FastAPI(
    title="FortiDashboard API",
    version="0.1.0",
    description="Backend API for FortiDashboard Fortinet integrations and widgets.",
    lifespan=lifespan,
)


def _session_middleware_options(settings) -> dict:
    return {
        "secret_key": settings.secret_key,
        "session_cookie": "f_session",
        "same_site": settings.session_cookie_samesite,
        "https_only": settings.session_cookie_secure,
    }


app.add_middleware(
    SessionMiddleware,
    **_session_middleware_options(_settings),
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(realtime.router, prefix="/api")
app.include_router(soc.router, prefix="/api")
app.include_router(soc_ingest.router, prefix="/api")
if _settings.enable_lab_demo_tools:
    app.include_router(lab_demo.router, prefix="/api")
app.include_router(widget_catalog.router, prefix="/api")
app.include_router(widgets.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(marketplace.router, prefix="/api")
