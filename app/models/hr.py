from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)

    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Row-level sensitivity (demo):
    # - when true, access is controlled by the "view_sensitive_data" permission.
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    performance_reviews: Mapped[list["PerformanceReview"]] = relationship(back_populates="employee")


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    # Denormalized for simple, automatic department filtering in the demo.
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)

    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    employee: Mapped[Employee] = relationship(back_populates="performance_reviews")

