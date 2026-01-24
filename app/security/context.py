from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthzContext:
    """
    Per-request authorization context.

    This is intentionally small and serializable-ish so it can be attached to:
    - request.state (FastAPI request lifetime)
    - Session.info (SQLAlchemy session lifetime)
    """

    user_id: int
    department_id: int
    roles: frozenset[str]
    permissions: frozenset[str]

    # Scope decisions (driven by config / decorators)
    filter_by_department: bool
    require_sensitive_permission: bool

    # Derived capabilities
    can_view_cross_department: bool
    can_view_sensitive_data: bool

