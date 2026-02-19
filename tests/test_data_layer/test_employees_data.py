"""
Tests for employee list/query data access (ORM).

See DATA_LAYER_TESTING.md.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.hr import Employee
from app.models.security import Department


def test_list_employees_ordered_by_id(db_session):
    dept = Department(name="IT", code="IT", description="IT")
    db_session.add(dept)
    db_session.flush()

    e1 = Employee(
        employee_id="E-1",
        first_name="A",
        last_name="B",
        email="a@b.com",
        department_id=dept.id,
    )
    e2 = Employee(
        employee_id="E-2",
        first_name="C",
        last_name="D",
        email="c@d.com",
        department_id=dept.id,
    )
    db_session.add_all([e1, e2])
    db_session.commit()

    stmt = select(Employee).order_by(Employee.id)
    result = list(db_session.scalars(stmt).all())

    assert len(result) == 2
    assert result[0].employee_id == "E-1"
    assert result[1].employee_id == "E-2"
