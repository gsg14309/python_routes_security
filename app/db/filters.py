from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria


@event.listens_for(Session, "do_orm_execute")
def _apply_authorization_filters(execute_state) -> None:
    """
    Transparent data scoping.

    This is the key piece that keeps existing query code unchanged:
        db.query(Employee).all()
    still returns department-scoped + sensitivity-scoped rows when required.
    """

    if not execute_state.is_select:
        return

    authz = execute_state.session.info.get("authz")
    if authz is None:
        return

    # Local import to avoid cycles.
    from app.models.hr import Employee, PerformanceReview  # noqa: WPS433 (local import)

    stmt = execute_state.statement

    if authz.filter_by_department and not authz.can_view_cross_department:
        dept_id = authz.department_id
        stmt = stmt.options(
            with_loader_criteria(Employee, lambda cls: cls.department_id == dept_id, include_aliases=True),
            with_loader_criteria(PerformanceReview, lambda cls: cls.department_id == dept_id, include_aliases=True),
        )

    if authz.require_sensitive_permission and not authz.can_view_sensitive_data:
        stmt = stmt.options(
            with_loader_criteria(Employee, lambda cls: cls.is_sensitive.is_(False), include_aliases=True),
            with_loader_criteria(PerformanceReview, lambda cls: cls.is_sensitive.is_(False), include_aliases=True),
        )

    execute_state.statement = stmt

