"""
Example: testing code that uses raw SQL (text()).

This module defines a small data-access function that uses raw SQL and tests it.
In real code you might have this in app/db/reports.py or similar. See DATA_LAYER_TESTING.md.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_department_user_counts(db: Session) -> list[dict]:
    """
    Example data-access function using raw SQL. Returns list of {code, user_count}.
    """
    result = db.execute(
        text("""
            SELECT d.code AS code, COUNT(u.id) AS user_count
            FROM departments d
            LEFT JOIN users u ON u.department_id = d.id
            GROUP BY d.id, d.code
        """)
    )
    return [{"code": row.code, "user_count": row.user_count} for row in result]


def test_get_department_user_counts(db_session):
    """Test raw SQL against in-memory SQLite with data inserted via ORM."""
    from app.models.security import Department, User

    hr = Department(name="HR", code="HR", description="HR")
    it = Department(name="IT", code="IT", description="IT")
    db_session.add_all([hr, it])
    db_session.flush()

    u1 = User(username="u1", email="u1@x.com", department_id=hr.id, is_active=True)
    u2 = User(username="u2", email="u2@x.com", department_id=hr.id, is_active=True)
    u3 = User(username="u3", email="u3@x.com", department_id=it.id, is_active=True)
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    stats = get_department_user_counts(db_session)

    assert len(stats) == 2
    codes = {s["code"] for s in stats}
    assert "HR" in codes
    assert "IT" in codes
    by_code = {s["code"]: s["user_count"] for s in stats}
    assert by_code["HR"] == 2
    assert by_code["IT"] == 1
