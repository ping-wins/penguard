from fastapi import FastAPI

from app.routers import auth, health, integrations, widget_catalog, widgets, workspaces

app = FastAPI(
    title="FortiDashboard API",
    version="0.1.0",
    description="Backend API for FortiDashboard Fortinet integrations and widgets.",
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(widget_catalog.router, prefix="/api")
app.include_router(widgets.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
