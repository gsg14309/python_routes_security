"""
Optional Microsoft Graph client for resolving roles when not in the token.

Background for newcomers:
    In Azure Entra ID you can assign users to "App Roles" or "Security Groups".
    If App Roles are configured, they appear directly in the token's ``roles``
    claim and this module is not needed. But if:
      - roles are not configured as token claims, or
      - the user belongs to so many groups that Azure can't fit them in the
        token (called "groups overage"),
    then the token arrives **without** a ``roles`` claim. In that case we call
    the Microsoft Graph API to ask "what groups is this user a member of?" and
    use those group names as roles.

    To call Graph we need an **app-only** (client credentials) token, which
    requires the ``AZURE_CLIENT_SECRET`` and the application permission
    ``User.Read.All`` or ``GroupMember.Read.All`` (granted in Azure portal
    under API Permissions for your app registration).

Uses client credentials (app-only) to call Graph. Required application permission:
- User.Read.All or GroupMember.Read.All to read user's group membership.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import EntraConfig

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# Types returned by the /memberOf endpoint that we treat as "role" sources.
# We deliberately skip administrativeUnit and other non-group types.
_GROUP_TYPES = frozenset({
    "#microsoft.graph.group",
    "#microsoft.graph.directoryRole",
})


class _AppTokenCache:
    """
    Minimal in-memory cache for the client-credentials Graph token.
    Avoids requesting a new app token on every Graph call.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_or_refresh(self, config: EntraConfig) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token
        self._token, expires_in = _request_app_token(config)
        # Cache with 5 min safety margin (tokens are usually valid ~1 hour)
        self._expires_at = now + max(expires_in - 300, 60)
        return self._token


_app_token_cache = _AppTokenCache()


def _request_app_token(config: EntraConfig) -> tuple[str, int]:
    """
    Obtain an app-only (client credentials) token for Microsoft Graph.

    Returns (access_token, expires_in_seconds).
    """
    if not config.client_secret:
        raise ValueError("AZURE_CLIENT_SECRET required for Graph fallback")
    url = TOKEN_URL_TEMPLATE.format(tenant_id=config.tenant_id)
    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    access_token = body.get("access_token")
    if not access_token:
        raise ValueError("No access_token in Graph token response")
    expires_in = int(body.get("expires_in", 3600))
    return access_token, expires_in


def resolve_roles_via_graph(user_oid: str, config: EntraConfig) -> list[str]:
    """
    Resolve roles (group / directory-role display names) for a user via
    Microsoft Graph.

    Calls ``GET /users/{oid}/memberOf`` and collects ``displayName`` from
    groups and directory roles. Handles pagination (``@odata.nextLink``)
    so users in 100+ groups are fully resolved.

    Requires application permission: ``User.Read.All`` or
    ``GroupMember.Read.All`` (or ``Directory.Read.All``).

    Returns a list of role strings (group display names). On Graph or
    network errors, logs a warning and returns an empty list (no roles)
    so the validator does not fail the request.
    """
    if not config.client_secret or not user_oid:
        return []

    try:
        token = _app_token_cache.get_or_refresh(config)
    except Exception as e:
        logger.warning("Graph app token failed: %s", type(e).__name__, exc_info=False)
        return []

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url: str | None = f"{GRAPH_BASE}/users/{user_oid}/memberOf"
    roles: list[str] = []

    try:
        while url:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning("Graph memberOf returned status=%s", resp.status_code)
                return roles  # return whatever we collected so far
            body = resp.json()

            for entry in body.get("value") or []:
                odata_type = entry.get("@odata.type", "")
                if odata_type not in _GROUP_TYPES:
                    continue  # skip administrativeUnit, servicePrincipal, etc.
                display_name = entry.get("displayName")
                if display_name:
                    roles.append(str(display_name))

            url = body.get("@odata.nextLink")  # None when no more pages
    except requests.RequestException as e:
        logger.warning("Graph request failed: %s", type(e).__name__, exc_info=False)

    return roles
