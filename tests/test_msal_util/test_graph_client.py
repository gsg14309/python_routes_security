"""Tests for Microsoft Graph client (mocked)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.msal_util.config import EntraConfig
from app.msal_util.graph_client import _app_token_cache, resolve_roles_via_graph


def _config(*, secret: str | None = "secret") -> EntraConfig:
    return EntraConfig(
        tenant_id="t",
        client_id="c",
        audience=None,
        clock_skew_seconds=60,
        jwks_cache_ttl_seconds=3600,
        graph_enabled=True,
        client_secret=secret,
    )


def setup_function():
    """Reset the app token cache before each test."""
    _app_token_cache._token = None
    _app_token_cache._expires_at = 0.0


def test_resolve_roles_empty_without_secret():
    assert resolve_roles_via_graph("oid-1", _config(secret=None)) == []


def test_resolve_roles_empty_without_oid():
    assert resolve_roles_via_graph("", _config()) == []


@patch("app.msal_util.graph_client.requests.post")
@patch("app.msal_util.graph_client.requests.get")
def test_resolve_roles_returns_group_display_names(mock_get, mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"access_token": "graph-token", "expires_in": 3600}
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "value": [
            {"@odata.type": "#microsoft.graph.group", "displayName": "Admins", "id": "g1"},
            {"@odata.type": "#microsoft.graph.group", "displayName": "Readers", "id": "g2"},
        ]
    }
    roles = resolve_roles_via_graph("user-oid-123", _config())
    assert roles == ["Admins", "Readers"]


@patch("app.msal_util.graph_client.requests.post")
@patch("app.msal_util.graph_client.requests.get")
def test_resolve_roles_filters_out_non_group_types(mock_get, mock_post):
    """Only groups and directoryRoles should be included; admin units skipped."""
    mock_post.return_value.json.return_value = {"access_token": "t", "expires_in": 3600}
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "value": [
            {"@odata.type": "#microsoft.graph.group", "displayName": "HR Team", "id": "g1"},
            {"@odata.type": "#microsoft.graph.administrativeUnit", "displayName": "West Region", "id": "au1"},
            {"@odata.type": "#microsoft.graph.directoryRole", "displayName": "Global Reader", "id": "dr1"},
        ]
    }
    roles = resolve_roles_via_graph("oid-1", _config())
    assert roles == ["HR Team", "Global Reader"]


@patch("app.msal_util.graph_client.requests.post")
@patch("app.msal_util.graph_client.requests.get")
def test_resolve_roles_handles_pagination(mock_get, mock_post):
    """Should follow @odata.nextLink for users in many groups."""
    mock_post.return_value.json.return_value = {"access_token": "t", "expires_in": 3600}

    page1 = MagicMock()
    page1.status_code = 200
    page1.json.return_value = {
        "value": [{"@odata.type": "#microsoft.graph.group", "displayName": "Group-A"}],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/oid/memberOf?$skiptoken=x",
    }
    page2 = MagicMock()
    page2.status_code = 200
    page2.json.return_value = {
        "value": [{"@odata.type": "#microsoft.graph.group", "displayName": "Group-B"}],
    }
    mock_get.side_effect = [page1, page2]

    roles = resolve_roles_via_graph("oid-1", _config())
    assert roles == ["Group-A", "Group-B"]
    assert mock_get.call_count == 2


@patch("app.msal_util.graph_client.requests.post")
def test_resolve_roles_returns_empty_on_token_failure(mock_post):
    mock_post.side_effect = requests.RequestException("network error")
    assert resolve_roles_via_graph("oid-1", _config()) == []
