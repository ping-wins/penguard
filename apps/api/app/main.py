import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.routers import (
    ai,
    audit,
    auth,
    health,
    integrations,
    marketplace,
    providers,
    soc,
    widget_catalog,
    widgets,
    workspaces,
)

logger = logging.getLogger(__name__)
_settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None
    if _settings.fortigate_ingestion_scheduler_enabled:
        task = asyncio.create_task(_fortigate_ingestion_scheduler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def _fortigate_ingestion_scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(integrations.run_due_fortigate_ingestions_once)
        except Exception:
            logger.exception("fortigate_ingestion_scheduler_tick_failed")
        await asyncio.sleep(_settings.fortigate_ingestion_scheduler_tick_seconds)


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
app.include_router(soc.router, prefix="/api")
app.include_router(widget_catalog.router, prefix="/api")
app.include_router(widgets.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(marketplace.router, prefix="/api")
