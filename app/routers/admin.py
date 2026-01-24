from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.security import Role, User
from app.schemas.security import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    stmt = select(User).options(selectinload(User.department), selectinload(User.roles)).order_by(User.id)
    return list(db.scalars(stmt).all())

