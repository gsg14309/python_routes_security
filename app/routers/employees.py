from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.hr import Employee
from app.schemas.hr import EmployeeOut
from app.schemas.security import UserOut
from app.security.dependencies import get_current_user

router = APIRouter(tags=["employees"])


@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)) -> UserOut:
    return user


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)) -> list[Employee]:
    # Filters are applied transparently via app/db/filters.py based on request authz.
    return list(db.scalars(select(Employee).order_by(Employee.id)).all())


@router.get("/employees/{id}", response_model=EmployeeOut)
def get_employee(id: int, db: Session = Depends(get_db)) -> Employee:
    employee = db.scalars(select(Employee).where(Employee.id == id)).first()
    if employee is None:
        # If an employee is outside your department or sensitive rows are hidden,
        # it will appear as "not found" (a common security practice).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee

