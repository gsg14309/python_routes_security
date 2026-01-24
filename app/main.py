from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.db import filters as _filters  # noqa: F401  (register SQLAlchemy filters)
from app.db.init_db import init_db
from app.logging_config import configure_app_logging
from app.routers import admin, decorator_demo, employees, health, performance_reviews
from app.security.config import load_security_config
from app.security.dependencies import enforce_security
from app.settings import get_settings


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        settings = get_settings()
        configure_app_logging(settings.log_level)

        import logging

        logger = logging.getLogger(__name__)
        logger.info("App startup beginning")

        app.state.security_config = load_security_config(settings.resolved_security_config_path())
        logger.info("Loaded security config: %s", settings.resolved_security_config_path())
        init_db()
        logger.info("Database initialized (tables ensured + seed if needed)")

        yield
        # Shutdown (nothing to clean up in this demo)

    # Global dependency: applies security with zero changes to route handlers.
    app = FastAPI(dependencies=[Depends(enforce_security)], lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(employees.router)
    app.include_router(performance_reviews.router)
    app.include_router(admin.router)
    app.include_router(decorator_demo.router)

    return app


app = create_app()

