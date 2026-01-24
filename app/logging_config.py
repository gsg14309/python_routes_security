from __future__ import annotations

import logging
from typing import Literal


def configure_app_logging(level: str = "INFO") -> None:
    """
    Minimal logging configuration for this repo.

    Notes:
    - We intentionally use stdlib logging (no extra deps).
    - Uvicorn already configures handlers; this function mainly sets levels for our package.
    - Set `APP_LOG_LEVEL=DEBUG` (or INFO/WARNING/ERROR) to control verbosity.
    """

    normalized = level.upper()
    logging.getLogger("app").setLevel(normalized)
    # Ensure child loggers under app.* inherit this level.
    logging.getLogger("app").propagate = True

