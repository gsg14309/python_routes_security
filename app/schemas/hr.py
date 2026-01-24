from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    first_name: str
    last_name: str
    email: str
    department_id: int
    position: str | None
    salary: float | None
    is_sensitive: bool
    hire_date: date | None
    created_at: datetime


class PerformanceReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    department_id: int
    review_date: date
    rating: int
    comments: str | None
    is_sensitive: bool
    created_at: datetime

