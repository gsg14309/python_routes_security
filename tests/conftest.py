"""
Pytest fixtures for the test suite.

Data-layer tests use an in-memory SQLite engine and a session that rolls back
after each test, so tests do not affect each other. See DATA_LAYER_TESTING.md.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture
def engine():
    """Create a fresh in-memory SQLite engine for each test."""
    return create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )


@pytest.fixture
def tables(engine):
    """Create all ORM tables on the test engine."""
    from app.db.base import Base
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(tables):
    """
    Provide a Session bound to the test DB; roll back after each test.

    Use this in tests that need a database (e.g. data layer tests). The
    transaction is rolled back so the next test gets a clean state.
    """
    connection = tables.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        class_=Session,
    )
    session = TestSession()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
