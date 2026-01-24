from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool
    department: DepartmentOut
    roles: list[RoleOut]

