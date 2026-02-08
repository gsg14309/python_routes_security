"""Configuration from environment variables. No hardcoded secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _getenv(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def _getenv_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class EntraConfig:
    """
    Azure Entra ID / MSAL configuration from environment.

    Required (for validation):
        AZURE_TENANT_ID: Tenant (directory) ID.
        AZURE_CLIENT_ID: API (backend) application (client) ID; used as audience.
        AZURE_AUDIENCE: Optional; if set, used as expected audience instead of client id.

    Optional:
        CLOCK_SKEW_SECONDS: Seconds of tolerance for exp/nbf (default 120).
        JWKS_CACHE_TTL_SECONDS: How long to cache JWKS (default 3600).

    For Microsoft Graph fallback (roles when not in token):
        MSAL_GRAPH_ENABLED: Set to 1 or true to enable Graph fallback.
        AZURE_CLIENT_SECRET: Client secret for app-only Graph calls.
    """

    tenant_id: str
    client_id: str
    audience: str | None  # if None, use client_id as audience
    clock_skew_seconds: int
    jwks_cache_ttl_seconds: int
    graph_enabled: bool
    client_secret: str | None

    @property
    def expected_audience(self) -> str:
        return self.audience if self.audience else self.client_id

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def jwks_uri(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

    @classmethod
    def from_environ(cls) -> EntraConfig:
        tenant = _getenv("AZURE_TENANT_ID")
        client = _getenv("AZURE_CLIENT_ID")
        if not tenant or not client:
            raise _config_error("AZURE_TENANT_ID and AZURE_CLIENT_ID must be set")
        return cls(
            tenant_id=tenant.strip(),
            client_id=client.strip(),
            audience=_strip_or_none(_getenv("AZURE_AUDIENCE")),
            clock_skew_seconds=_getenv_int("CLOCK_SKEW_SECONDS", 120),
            jwks_cache_ttl_seconds=_getenv_int("JWKS_CACHE_TTL_SECONDS", 3600),
            graph_enabled=_getenv("MSAL_GRAPH_ENABLED", "").strip().lower() in ("1", "true", "yes"),
            client_secret=_strip_or_none(_getenv("AZURE_CLIENT_SECRET")),
        )


def _strip_or_none(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def _config_error(msg: str) -> Exception:
    return ValueError(msg)
