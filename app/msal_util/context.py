"""Serializable context produced after validating an Entra access token."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenContext:
    """
    Small, serializable context for use by the rest of the application.

    Populated from validated JWT claims and optional Microsoft Graph fallback.
    """

    user_id: str
    """Canonical user id from token (sub or oid)."""

    roles: tuple[str, ...]
    """App roles (and/or groups if resolved via Graph)."""

    department: str | None
    """Department from token custom claim or Graph; may be None if not configured."""

    scopes: tuple[str, ...]
    """OAuth2 scopes from token (scp claim)."""

    preferred_username: str | None = None
    """Display name from token; optional, for UI only."""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict."""
        return {
            "user_id": self.user_id,
            "roles": list(self.roles),
            "department": self.department,
            "scopes": list(self.scopes),
            "preferred_username": self.preferred_username,
        }
