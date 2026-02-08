"""Tests for TokenContext."""

import pytest

from app.msal_util.context import TokenContext


def test_token_context_to_dict():
    ctx = TokenContext(
        user_id="oid-123",
        roles=("admin", "reader"),
        department="Engineering",
        scopes=("read", "write"),
        preferred_username="user@example.com",
    )
    d = ctx.to_dict()
    assert d["user_id"] == "oid-123"
    assert d["roles"] == ["admin", "reader"]
    assert d["department"] == "Engineering"
    assert d["scopes"] == ["read", "write"]
    assert d["preferred_username"] == "user@example.com"


def test_token_context_department_none():
    ctx = TokenContext(
        user_id="sub-1",
        roles=(),
        department=None,
        scopes=(),
    )
    assert ctx.department is None
    assert ctx.to_dict()["department"] is None
