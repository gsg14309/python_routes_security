"""
Tests for user-loading data access (ORM).

Uses db_session fixture: in-memory SQLite, rolled back after each test.
See DATA_LAYER_TESTING.md.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.security import Department, Role, User
from app.security.auth import load_user


def test_load_user_returns_user_with_department_and_roles(db_session):
    # Arrange: create department, role, user (like init_db does)
    dept = Department(name="IT", code="IT", description="IT Dept")
    db_session.add(dept)
    db_session.flush()

    role = Role(name="admin", description="Admin role")
    db_session.add(role)
    db_session.flush()

    user = User(
        username="testuser",
        email="test@example.com",
        department_id=dept.id,
        is_active=True,
    )
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()

    # Act
    loaded = load_user(db_session, user.id)

    # Assert
    assert loaded.id == user.id
    assert loaded.username == "testuser"
    assert loaded.department is not None
    assert loaded.department.code == "IT"
    assert len(loaded.roles) == 1
    assert loaded.roles[0].name == "admin"


def test_load_user_raises_when_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        load_user(db_session, 99999)
    assert exc_info.value.status_code == 401


def test_load_user_raises_when_inactive(db_session):
    dept = Department(name="IT", code="IT", description="IT")
    db_session.add(dept)
    db_session.flush()
    user = User(
        username="inactive",
        email="inactive@example.com",
        department_id=dept.id,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        load_user(db_session, user.id)
    assert exc_info.value.status_code == 401
