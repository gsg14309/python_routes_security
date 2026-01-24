from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.hr import Employee, PerformanceReview
from app.schemas.hr import EmployeeOut, PerformanceReviewOut
from app.security.decorators import filter_by_department, require_roles, require_sensitive_permission

router = APIRouter(prefix="/decorator-demo", tags=["decorator_demo"])


@router.get("/employees", response_model=list[EmployeeOut])
@require_roles(["department_manager"])
@filter_by_department()
def decorator_scoped_employees(db: Session = Depends(get_db)) -> list[Employee]:
    # No config entry required: decorators provide rule metadata, enforced globally.
    return list(db.scalars(select(Employee).order_by(Employee.id)).all())


@router.get("/performance-reviews", response_model=list[PerformanceReviewOut])
@require_roles(["hr_manager", "admin"])
@require_sensitive_permission()
def decorator_sensitive_reviews(db: Session = Depends(get_db)) -> list[PerformanceReview]:
    return list(db.scalars(select(PerformanceReview).order_by(PerformanceReview.id)).all())

