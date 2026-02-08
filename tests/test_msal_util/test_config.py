"""Tests for EntraConfig from environment."""

import os

import pytest

from app.msal_util.config import EntraConfig


def test_config_requires_tenant_and_client():
    with pytest.raises(ValueError, match="AZURE_TENANT_ID and AZURE_CLIENT_ID"):
        with _env({}):
            EntraConfig.from_environ()


def test_config_from_environ():
    env = {
        "AZURE_TENANT_ID": "tenant-1",
        "AZURE_CLIENT_ID": "client-1",
    }
    with _env(env):
        cfg = EntraConfig.from_environ()
    assert cfg.tenant_id == "tenant-1"
    assert cfg.client_id == "client-1"
    assert cfg.expected_audience == "client-1"
    assert cfg.issuer == "https://login.microsoftonline.com/tenant-1/v2.0"
    assert cfg.jwks_uri == "https://login.microsoftonline.com/tenant-1/discovery/v2.0/keys"
    assert cfg.clock_skew_seconds == 120
    assert cfg.jwks_cache_ttl_seconds == 3600
    assert cfg.graph_enabled is False


def test_config_audience_override():
    env = {
        "AZURE_TENANT_ID": "t",
        "AZURE_CLIENT_ID": "c",
        "AZURE_AUDIENCE": "api://my-app",
    }
    with _env(env):
        cfg = EntraConfig.from_environ()
    assert cfg.expected_audience == "api://my-app"


def test_config_graph_enabled():
    env = {
        "AZURE_TENANT_ID": "t",
        "AZURE_CLIENT_ID": "c",
        "MSAL_GRAPH_ENABLED": "true",
    }
    with _env(env):
        cfg = EntraConfig.from_environ()
    assert cfg.graph_enabled is True


def _env(env: dict):
    class _Env:
        def __enter__(self):
            self._saved = os.environ.copy()
            os.environ.clear()
            os.environ.update(env)
            return self

        def __exit__(self, *args):
            os.environ.clear()
            os.environ.update(self._saved)
            return False

    return _Env()
