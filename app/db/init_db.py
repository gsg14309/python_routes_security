from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.hr import Employee, PerformanceReview
from app.models.security import Department, Role, User


def init_db() -> None:
    """
    Create tables + seed demo data.

    This is deliberately small and deterministic so you can quickly try the
    security behavior without additional setup.
    """

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if _has_seed_data(db):
            return
        _seed(db)


def _has_seed_data(db: Session) -> bool:
    return db.execute(select(Department.id).limit(1)).first() is not None


def _seed(db: Session) -> None:
    # Departments
    hr = Department(name="Human Resources", code="HR", description="HR Department")
    it = Department(name="Information Technology", code="IT", description="IT Department")
    fin = Department(name="Finance", code="FIN", description="Finance Department")
    db.add_all([hr, it, fin])
    db.flush()

    # Roles
    admin = Role(name="admin", description="System administrator")
    hr_manager = Role(name="hr_manager", description="HR manager")
    dept_manager = Role(name="department_manager", description="Department manager")
    employee = Role(name="employee", description="Regular employee")
    db.add_all([admin, hr_manager, dept_manager, employee])
    db.flush()

    # Users
    u1 = User(username="alice_admin", email="alice.admin@example.com", department_id=hr.id, is_active=True)
    u1.roles.append(admin)

    u2 = User(username="harry_hr", email="harry.hr@example.com", department_id=hr.id, is_active=True)
    u2.roles.append(hr_manager)

    u3 = User(username="mona_mgr_it", email="mona.itmgr@example.com", department_id=it.id, is_active=True)
    u3.roles.append(dept_manager)

    u4 = User(username="ed_it", email="ed.it@example.com", department_id=it.id, is_active=True)
    u4.roles.append(employee)

    u5 = User(username="fran_fin", email="fran.fin@example.com", department_id=fin.id, is_active=True)
    u5.roles.append(employee)

    db.add_all([u1, u2, u3, u4, u5])
    db.flush()

    # Employees (some sensitive rows)
    e1 = Employee(
        employee_id="E-1001",
        first_name="Ed",
        last_name="Engineer",
        email="ed.engineer@example.com",
        department_id=it.id,
        position="Software Engineer",
        salary=120000.00,
        is_sensitive=True,
        hire_date=date(2022, 6, 1),
    )
    e2 = Employee(
        employee_id="E-1002",
        first_name="Ivy",
        last_name="IT",
        email="ivy.it@example.com",
        department_id=it.id,
        position="IT Analyst",
        salary=85000.00,
        is_sensitive=False,
        hire_date=date(2023, 2, 15),
    )
    e3 = Employee(
        employee_id="E-2001",
        first_name="Fran",
        last_name="Finance",
        email="fran.finance@example.com",
        department_id=fin.id,
        position="Accountant",
        salary=90000.00,
        is_sensitive=True,
        hire_date=date(2021, 9, 10),
    )
    db.add_all([e1, e2, e3])
    db.flush()

    # Performance reviews (default sensitive)
    r1 = PerformanceReview(
        employee_id=e1.id,
        department_id=it.id,
        review_date=date(2025, 12, 15),
        rating=5,
        comments="Excellent performance.",
        is_sensitive=True,
    )
    r2 = PerformanceReview(
        employee_id=e2.id,
        department_id=it.id,
        review_date=date(2025, 11, 20),
        rating=3,
        comments="Meets expectations.",
        is_sensitive=True,
    )
    r3 = PerformanceReview(
        employee_id=e3.id,
        department_id=fin.id,
        review_date=date(2025, 10, 10),
        rating=4,
        comments="Strong performer.",
        is_sensitive=True,
    )
    db.add_all([r1, r2, r3])

    db.commit()

