from __future__ import annotations

from fastapi import Depends, FastAPI

from app.db import filters as _filters  # noqa: F401  (register SQLAlchemy filters)
from app.db.init_db import init_db
from app.routers import admin, decorator_demo, employees, health, performance_reviews
from app.security.config import load_security_config
from app.security.dependencies import enforce_security
from app.settings import get_settings


def create_app() -> FastAPI:
    # Global dependency: applies security with zero changes to route handlers.
    app = FastAPI(dependencies=[Depends(enforce_security)])

    app.include_router(health.router)
    app.include_router(employees.router)
    app.include_router(performance_reviews.router)
    app.include_router(admin.router)
    app.include_router(decorator_demo.router)

    @app.on_event("startup")
    def _startup() -> None:
        settings = get_settings()
        app.state.security_config = load_security_config(settings.resolved_security_config_path())
        init_db()

    return app


app = create_app()

