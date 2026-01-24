from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.security import User
from app.security.config import SecurityConfig

logger = logging.getLogger(__name__)


def extract_user_id(request: Request, config: SecurityConfig) -> int | None:
    """
    Demo auth: extract bearer token and treat it as a user_id.

    - Input: `Authorization: Bearer <token>`
    - Demo behavior: `<token>` must be an integer user id
    - Production behavior (documented only): validate token + resolve roles via Azure AD
    """

    header_name = config.auth.authorization_header
    bearer_prefix = config.auth.bearer_prefix

    raw = request.headers.get(header_name)
    if not raw:
        logger.info("Missing Authorization header (auth required) path=%s method=%s", request.url.path, request.method)
        return None

    prefix = f"{bearer_prefix} "
    if not raw.startswith(prefix):
        logger.warning("Invalid Authorization header format path=%s method=%s", request.url.path, request.method)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {header_name}. Expected '{bearer_prefix} <token>'.",
        )

    token = raw[len(prefix) :].strip()
    if not token:
        logger.warning("Empty bearer token path=%s method=%s", request.url.path, request.method)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {header_name}. Missing token after '{bearer_prefix}'.",
        )

    try:
        return int(token)
    except ValueError as exc:  # pragma: no cover (simple demo)
        logger.warning("Bearer token not an int (demo expects user_id) path=%s method=%s", request.url.path, request.method)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bearer token for demo (expected integer user id).",
        ) from exc


def load_user(db: Session, user_id: int) -> User:
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.department),
            selectinload(User.roles),
        )
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive user")

    return user

