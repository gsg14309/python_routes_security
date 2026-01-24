from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.security import User
from app.security.auth import extract_user_id, load_user
from app.security.config import SecurityConfig
from app.security.context import AuthzContext


def get_security_config(request: Request) -> SecurityConfig:
    config = getattr(request.app.state, "security_config", None)
    if config is None:
        raise RuntimeError("Security config not loaded. Did app startup run?")
    return config


def get_current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def enforce_security(
    request: Request,
    config: SecurityConfig = Depends(get_security_config),
    db: Session = Depends(get_db, use_cache=False),
) -> None:
    """
    Global security dependency (PRIMARY, configuration-driven).

    Why dependency (not middleware)?
    - Runs after routing, so we can also *optionally* read decorator metadata.
    - Still requires **zero changes** to existing route handlers when added globally.
    """

    path = request.url.path
    method = request.method.upper()

    rule = config.match(path, method)

    # Optional decorator metadata (alternative example).
    endpoint = request.scope.get("endpoint")
    decorator_roles = set(getattr(endpoint, "__security_required_roles__", set())) if endpoint else set()
    decorator_filter_dept = bool(getattr(endpoint, "__security_filter_by_department__", False)) if endpoint else False
    decorator_sensitive = bool(getattr(endpoint, "__security_require_sensitive_permission__", False)) if endpoint else False

    auth_required = rule.auth_required or bool(decorator_roles) or decorator_filter_dept or decorator_sensitive
    if not auth_required:
        return

    user_id = extract_user_id(request, config)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user id")

    user = load_user(db, user_id)
    request.state.user = user

    user_roles = {r.name for r in user.roles}
    user_permissions = _derive_permissions(user, config)

    required_roles = set(rule.required_roles) | decorator_roles
    if required_roles and not (user_roles & required_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient role. Required one of: {sorted(required_roles)}",
        )

    filter_by_department = rule.filter_by_department or decorator_filter_dept
    require_sensitive_permission = rule.require_sensitive_permission or decorator_sensitive

    can_view_cross_department = "view_cross_department" in user_permissions
    can_view_sensitive_data = "view_sensitive_data" in user_permissions

    request.state.authz = AuthzContext(
        user_id=user.id,
        department_id=user.department_id,
        roles=frozenset(user_roles),
        permissions=frozenset(user_permissions),
        filter_by_department=filter_by_department,
        require_sensitive_permission=require_sensitive_permission,
        can_view_cross_department=can_view_cross_department,
        can_view_sensitive_data=can_view_sensitive_data,
    )


def _derive_permissions(user: User, config: SecurityConfig) -> set[str]:
    """
    Derive capabilities from configuration only.

    Rationale:
    - In the target integration, roles come from the identity provider (Azure AD).
    - Permissions are treated as *capabilities* derived from roles via config.
    - We keep this logic purely config-driven to avoid coupling to DB schemas.
    """

    perms: set[str] = set()

    # From config mappings
    role_names = {r.name for r in user.roles}
    for permission_name in config.model.permissions.keys():
        if role_names & set(config.permission_roles(permission_name)):
            perms.add(permission_name)

    return perms

