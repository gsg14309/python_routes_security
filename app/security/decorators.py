from __future__ import annotations

from collections.abc import Callable


def require_roles(roles: list[str]) -> Callable:
    """
    Decorator-style API (ALTERNATIVE EXAMPLE).

    Implementation detail:
    - This decorator does NOT perform auth itself.
    - It attaches metadata that our global security dependency can read
      *after* routing (during dependency resolution).
    """

    def decorator(fn: Callable) -> Callable:
        existing = set(getattr(fn, "__security_required_roles__", set()))
        setattr(fn, "__security_required_roles__", existing | set(roles))
        return fn

    return decorator


def filter_by_department() -> Callable:
    """
    Decorator-style API (ALTERNATIVE EXAMPLE).

    Attaches metadata used to enable department scoping for this endpoint.
    """

    def decorator(fn: Callable) -> Callable:
        setattr(fn, "__security_filter_by_department__", True)
        return fn

    return decorator


def require_sensitive_permission() -> Callable:
    """
    Decorator-style API (ALTERNATIVE EXAMPLE).

    Attaches metadata used to enable sensitive-row filtering for this endpoint.
    """

    def decorator(fn: Callable) -> Callable:
        setattr(fn, "__security_require_sensitive_permission__", True)
        return fn

    return decorator

