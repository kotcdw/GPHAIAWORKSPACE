"""Auth schemas: register, login, me, profile, password."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.core.validators import OptEmail
from app.modules.users.schemas import UserOut


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    company: str = Field(default="", max_length=255)


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