"""
Validate Entra-signed JWT (access token) and extract claims.

Background for newcomers:
    When your SPA sends ``Authorization: Bearer <token>`` to this API, the
    token is a JWT (JSON Web Token) signed by Azure Entra ID. Before we trust
    **anything** in that token we must:

    1. Verify the **signature** (proves it really came from Entra, not forged).
    2. Check the **issuer** (``iss``) matches our Azure tenant.
    3. Check the **audience** (``aud``) matches our API's app registration.
    4. Check it hasn't **expired** (``exp``) and isn't used before its start
       time (``nbf``).

    Only after all four checks pass do we read the claims (user id, roles,
    scopes, etc.) and build a ``TokenContext`` for the rest of the app.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt

from .config import EntraConfig
from .context import TokenContext
from .graph_client import resolve_roles_via_graph
from .jwks_cache import JWKSCache

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when token validation fails. Do not log the token."""

    pass


def _get_kid(token: str) -> str | None:
    """
    Read the ``kid`` (Key ID) from the JWT header **without** validating the
    token. We need the kid to look up the correct public key in the JWKS.
    """
    try:
        header = jwt.get_unverified_header(token)
        return header.get("kid") if isinstance(header, dict) else None
    except Exception:
        return None


def _extract_claims(payload: dict[str, Any]) -> TokenContext:
    """
    Build a ``TokenContext`` from a validated JWT payload.

    Claim mapping notes (Azure Entra ID v2.0 access tokens):

    * **oid** — Object ID. The immutable, tenant-wide identifier for the user.
      Same value regardless of which app registration issued the token.
      Preferred for backend user identity and for Microsoft Graph calls.
    * **sub** — Subject. A *pairwise* identifier: unique per user **per app
      registration**. Different apps see different ``sub`` values for the same
      user. Not suitable as a cross-app user id.
    * **roles** — App Roles assigned to the user (configured in the API's app
      registration under "App roles"). List of strings, e.g. ``["Admin"]``.
    * **scp** — Scopes (delegated permissions). Space-separated string in
      access tokens, e.g. ``"User.Read Files.Read"``.
    * **department** — Not present by default. Must be added as an optional
      claim or claims-mapping policy in Azure. May be None.
    * **preferred_username** — Usually the user's UPN / email. For display
      only; do not use for authorization.
    """

    # Prefer oid (stable, tenant-wide) over sub (pairwise, per-app).
    user_id = payload.get("oid") or payload.get("sub") or ""
    user_id = str(int(user_id)) if isinstance(user_id, (int, float)) else str(user_id)

    roles: list[str] = []
    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        roles = [str(r) for r in raw_roles]
    elif isinstance(raw_roles, str):
        roles = [raw_roles]

    department: str | None = None
    if "department" in payload and payload["department"]:
        department = str(payload["department"])

    scopes: list[str] = []
    scp = payload.get("scp")
    if isinstance(scp, str):
        scopes = [s.strip() for s in scp.split() if s.strip()]
    elif isinstance(scp, list):
        scopes = [str(s) for s in scp]

    preferred_username = payload.get("preferred_username")
    if preferred_username is not None:
        preferred_username = str(preferred_username)

    return TokenContext(
        user_id=user_id,
        roles=tuple(roles),
        department=department,
        scopes=tuple(scopes),
        preferred_username=preferred_username,
    )


class EntraTokenValidator:
    """
    Validates Azure Entra ID access tokens and extracts claims.

    Uses JWKS from the Entra discovery endpoint with a configurable TTL cache.
    Validates signature, issuer, audience, and exp/nbf before using any claim.
    """

    def __init__(self, config: EntraConfig | None = None) -> None:
        self._config = config or EntraConfig.from_environ()
        self._jwks = JWKSCache(
            self._config.jwks_uri,
            self._config.jwks_cache_ttl_seconds,
        )

    def validate_and_extract(self, token: str) -> TokenContext:
        """
        Validate the access token and return a TokenContext.

        This is the instance method that does the real work. There is also a
        module-level function ``validate_and_extract(token, config=...)`` in
        this file that creates a validator and calls this method — use that
        when you want a one-liner without holding a validator instance (e.g.
        config from environment). Use this method when you already have an
        ``EntraTokenValidator`` (e.g. for tests or when reusing one instance).
        Raises ValidationError if signature, issuer, audience, or lifetime
        checks fail.
        """
        kid = _get_kid(token)
        if not kid:
            logger.debug("Token missing or invalid kid")
            raise ValidationError("Invalid token: missing key id")

        signing_key = self._jwks.get_signing_key(kid)
        if signing_key is None:
            logger.debug("No signing key found for kid")
            raise ValidationError("Invalid token: unknown signing key")

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._config.expected_audience,
                issuer=self._config.issuer,
                leeway=self._config.clock_skew_seconds,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError as e:
            logger.info("Token expired")
            raise ValidationError("Token expired") from e
        except jwt.InvalidIssuerError as e:
            logger.info("Token invalid issuer")
            raise ValidationError("Invalid token: issuer") from e
        except jwt.InvalidAudienceError as e:
            logger.info("Token invalid audience")
            raise ValidationError("Invalid token: audience") from e
        except jwt.InvalidTokenError as e:
            logger.info("Token invalid: %s", type(e).__name__)
            raise ValidationError("Invalid token") from e

        ctx = _extract_claims(payload)

        # Optional: resolve roles via Microsoft Graph when not in token
        if not ctx.roles and self._config.graph_enabled:
            oid = payload.get("oid") or payload.get("sub")
            if oid:
                graph_roles = resolve_roles_via_graph(str(oid), self._config)
                if graph_roles:
                    ctx = TokenContext(
                        user_id=ctx.user_id,
                        roles=tuple(graph_roles),
                        department=ctx.department,
                        scopes=ctx.scopes,
                        preferred_username=ctx.preferred_username,
                    )
        return ctx


def validate_and_extract(token: str, config: EntraConfig | None = None) -> TokenContext:
    """
    Convenience function: validate bearer token and return TokenContext.

    Creates an ``EntraTokenValidator`` (loading config from the environment
    if ``config`` is None) and delegates to its ``validate_and_extract``
    instance method. Prefer this when you need a single call without
    managing a validator instance; use ``EntraTokenValidator`` directly
    when you want to reuse one validator (and its JWKS cache) for many tokens.
    """
    validator = EntraTokenValidator(config=config)
    return validator.validate_and_extract(token)
