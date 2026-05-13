from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.routers import (
    ai,
    audit,
    auth,
    health,
    integrations,
    providers,
    soc,
    widget_catalog,
    widgets,
    workspaces,
)

app = FastAPI(
    title="FortiDashboard API",
    version="0.1.0",
    description="Backend API for FortiDashboard Fortinet integrations and widgets.",
)

_settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.secret_key,
    session_cookie="f_session",
    same_site="lax",
    https_only=False,
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
