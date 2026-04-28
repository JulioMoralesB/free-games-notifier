"""FastAPI application instance, router registration, and dashboard mount."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import checks, games, notifications, system

app = FastAPI(
    title="Free Games Notifier API",
    description="REST API for monitoring and managing the Free Games Notifier service.",
    version="1.0.0",
)

# Register endpoint groups
app.include_router(system.router)
app.include_router(games.router)
app.include_router(notifications.router)
app.include_router(checks.router)

# ---------------------------------------------------------------------------
# Dashboard – serve the pre-built React/TypeScript frontend
# ---------------------------------------------------------------------------

_dashboard_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard",
    "dist",
)
if os.path.isdir(_dashboard_dist):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_dist, html=True), name="dashboard")
