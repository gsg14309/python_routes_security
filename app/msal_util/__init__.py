"""
Standalone utility to validate Azure Entra ID access tokens and extract claims.

This package has no dependency on other app packages (app.db, app.security, etc.).
Use validate_and_extract() with a bearer token string to get a TokenContext.
"""

from .config import EntraConfig
from .context import TokenContext
from .validator import EntraTokenValidator, ValidationError, validate_and_extract

__all__ = [
    "EntraConfig",
    "TokenContext",
    "EntraTokenValidator",
    "ValidationError",
    "validate_and_extract",
]
