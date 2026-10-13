"""Auth schemas: register, login, me, profile, password."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.validators import OptEmail, password_problems
from app.modules.users.schemas import UserOut


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    company: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def _strong_password(self) -> RegisterRequest:
        problem = password_problems(self.password, self.username)
        if problem:
            raise ValueError(f"Password {problem}")
        return self


class LoginRequest(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


class ProfileUpdate(BaseModel):
    email: OptEmail = None
    full_name: str | None = Field(default=None, max_length=255)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        problem = password_problems(value)
        if problem:
            raise ValueError(problem)
        return value