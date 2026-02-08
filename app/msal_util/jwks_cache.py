"""
JWKS fetch and cache with TTL. No per-request fetches.

Background for newcomers:
    Azure Entra ID signs every access token with a private RSA key. Your API
    needs the matching **public** key to verify the signature. Entra publishes
    its current public keys at a well-known URL (the JWKS endpoint). This
    module fetches those keys and caches them so we don't call Entra on every
    single request.

    Azure periodically **rotates** signing keys (old keys expire, new ones are
    added). If a token arrives signed with a key we haven't seen yet (the
    ``kid`` — Key ID — in the token header doesn't match anything in our
    cache), we force-refresh the cache once and try again before rejecting.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from jwt import PyJWK

logger = logging.getLogger(__name__)


class JWKSCache:
    """
    In-memory cache of JWKS (JSON Web Key Set) with TTL.

    Fetches from the Entra discovery endpoint and caches for ``ttl_seconds``.
    On cache miss (unknown ``kid``), the cache is refreshed once to handle
    Azure key rotation before returning None.
    """

    def __init__(self, jwks_uri: str, ttl_seconds: int) -> None:
        self._uri = jwks_uri
        self._ttl = ttl_seconds
        self._data: dict[str, Any] | None = None
        self._fetched_at: float = 0.0

    def _fetch(self) -> dict[str, Any]:
        resp = requests.get(self._uri, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _refresh(self) -> dict[str, Any]:
        """Force-refresh the cache regardless of TTL."""
        self._data = self._fetch()
        self._fetched_at = time.monotonic()
        logger.debug("JWKS cache refreshed uri=%s", self._uri)
        return self._data

    def _ensure_fresh(self) -> dict[str, Any]:
        """Return cached data, refreshing only when TTL has elapsed."""
        now = time.monotonic()
        if self._data is None or (now - self._fetched_at) >= self._ttl:
            return self._refresh()
        return self._data

    def _find_key(self, kid: str, data: dict[str, Any]) -> PyJWK | None:
        """Look up a key by kid in the given JWKS data."""
        for key_dict in data.get("keys") or []:
            if key_dict.get("kid") == kid:
                return PyJWK.from_dict(key_dict)
        return None

    def get_signing_key(self, kid: str) -> PyJWK | None:
        """
        Return the JWK for the given key id.

        If ``kid`` is not in the cached key set, the cache is refreshed once
        (to handle Azure key rotation) before returning None.
        """
        data = self._ensure_fresh()
        key = self._find_key(kid, data)
        if key is not None:
            return key

        # Key not found — Azure may have rotated keys. Refresh once.
        logger.info("kid not in cached JWKS; refreshing for possible key rotation")
        data = self._refresh()
        return self._find_key(kid, data)
