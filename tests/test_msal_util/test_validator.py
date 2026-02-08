"""Tests for token validation and claim extraction."""

import time
from unittest.mock import patch

import jwt
import pytest
from jwt.api_jwk import PyJWK

from app.msal_util.config import EntraConfig
from app.msal_util.context import TokenContext
from app.msal_util.validator import EntraTokenValidator, ValidationError, _extract_claims


def test_extract_claims():
    payload = {
        "sub": "pairwise-sub-123",
        "oid": "oid-123",
        "roles": ["admin", "reader"],
        "department": "HR",
        "scp": "read write",
        "preferred_username": "user@example.com",
    }
    ctx = _extract_claims(payload)
    assert ctx.user_id == "oid-123"  # oid takes precedence (stable, tenant-wide)
    assert ctx.roles == ("admin", "reader")
    assert ctx.department == "HR"
    assert ctx.scopes == ("read", "write")
    assert ctx.preferred_username == "user@example.com"


def test_extract_claims_uses_sub_when_no_oid():
    """Falls back to sub when oid is absent (non-Azure issuers)."""
    payload = {"sub": "sub-456", "roles": []}
    ctx = _extract_claims(payload)
    assert ctx.user_id == "sub-456"


def test_extract_claims_scp_list():
    payload = {"oid": "x", "scp": ["read", "write"]}
    ctx = _extract_claims(payload)
    assert ctx.scopes == ("read", "write")


def test_validator_invalid_token_raises():
    config = EntraConfig(
        tenant_id="t",
        client_id="c",
        audience=None,
        clock_skew_seconds=60,
        jwks_cache_ttl_seconds=3600,
        graph_enabled=False,
        client_secret=None,
    )
    validator = EntraTokenValidator(config=config)
    with pytest.raises(ValidationError):
        validator.validate_and_extract("not-a-jwt")


def test_validator_missing_kid_raises():
    # Build a JWT with no kid in header (key long enough to avoid HMAC warning)
    payload = {"sub": "u", "iss": "https://login.microsoftonline.com/t/v2.0", "aud": "c", "exp": time.time() + 300, "nbf": time.time() - 60}
    token = jwt.encode(payload, "x" * 32, algorithm="HS256", headers={})
    config = EntraConfig(
        tenant_id="t",
        client_id="c",
        audience=None,
        clock_skew_seconds=60,
        jwks_cache_ttl_seconds=3600,
        graph_enabled=False,
        client_secret=None,
    )
    validator = EntraTokenValidator(config=config)
    with pytest.raises(ValidationError):
        validator.validate_and_extract(token)


def test_validator_valid_token_roundtrip():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    kid = "test-key-1"
    jwk["kid"] = kid

    now = int(time.time())
    payload = {
        "sub": "user-1",
        "oid": "oid-1",
        "roles": ["Admin"],
        "iss": "https://login.microsoftonline.com/tenant-1/v2.0",
        "aud": "api-client-id",
        "exp": now + 3600,
        "nbf": now - 120,
    }
    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )

    config = EntraConfig(
        tenant_id="tenant-1",
        client_id="api-client-id",
        audience=None,
        clock_skew_seconds=120,
        jwks_cache_ttl_seconds=3600,
        graph_enabled=False,
        client_secret=None,
    )

    with patch("app.msal_util.validator.JWKSCache") as mock_cache:
        mock_jwk = PyJWK.from_dict(jwk)
        mock_cache.return_value.get_signing_key.return_value = mock_jwk
        validator = EntraTokenValidator(config=config)
        ctx = validator.validate_and_extract(token)
    assert ctx.user_id == "oid-1"  # oid preferred over sub for Azure
    assert ctx.roles == ("Admin",)
    assert ctx.department is None
    assert ctx.scopes == ()
