"""Users schemas: user administration records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.enums import ReviewLevel, Role
from app.core.schemas import ORMModel
from app.core.validators import OptEmail, password_problems


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
    review_level: ReviewLevel | None = None
    mfa_enabled: bool = False
    work_entity_id: int | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _strong_password(self) -> UserCreate:
        problem = password_problems(self.password, self.username)
        if problem:
            raise ValueError(f"Password {problem}")
        return self
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
    # "Manager" / "CAE" sets the report review level; "" clears it.
    review_level: Literal["", "Manager", "CAE"] | None = None
    # True clears the user's MFA enrolment (lost phone).
    reset_mfa: bool | None = None
    # Where the user is based (an entity, normally a port); send null to clear.
    work_entity_id: int | None = None

    @field_validator("password")
    @classmethod
    def _strong_password(cls, value: str | None) -> str | None:
        problem = password_problems(value) if value else None
        if problem:
            raise ValueError(problem)
        return value