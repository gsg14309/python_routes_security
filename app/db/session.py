from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import get_settings


_settings = get_settings()

engine = create_engine(
    _settings.resolved_db_url(),
    connect_args={"check_same_thread": False} if _settings.resolved_db_url().startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db(request: Request) -> Generator[Session, None, None]:
    """
    Main DB dependency.

    Key design goal (minimal disruption):
    - Existing code that does `db.query(Model).all()` should still be scoped correctly.
    - We achieve this via SQLAlchemy `do_orm_execute` filters that read `Session.info["authz"]`.
    """

    db = SessionLocal()
    try:
        authz = getattr(getattr(request, "state", None), "authz", None)
        if authz is not None:
            db.info["authz"] = authz
        yield db
    finally:
        db.close()

