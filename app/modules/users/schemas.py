"""Users schemas: user administration records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import Role
from app.core.schemas import ORMModel
from app.core.validators import OptEmail


class UserOut(ORMModel):
    id: int
    username: str
    role: Role
    email: str
    full_name: str
    first_name: str
    last_name: str
    company: str
    is_active: bool
    locked_until: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    company: str = Field(default="", max_length=255)
    role: Role = Role.Auditee
    is_active: bool = True


class UserUpdate(BaseModel):
    email: OptEmail = None
    full_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)