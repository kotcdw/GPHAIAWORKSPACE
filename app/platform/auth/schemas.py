"""Auth schemas: register, login, me, profile, password."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.validators import OptEmail, password_problems
from app.platform.users.schemas import UserOut


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
    # 6-digit authenticator code, required when the account has MFA enabled.
    otp: str | None = None


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str
    # True when the role requires MFA and the user has not set it up yet.
    mfa_setup_required: bool = False
    # Fine-grained permissions of the user's job role (drive what the screens offer).
    permissions: list[str] = []
    # Minutes without activity before the session ends (0 = no limit); the web app warns a minute before.
    idle_timeout_minutes: int = 0
    regional: dict = {}


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisable(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=8)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class ProfileUpdate(BaseModel):
    email: OptEmail = None
    full_name: str | None = Field(default=None, max_length=255)
    # Where the user is based (an entity, normally a port); send null to clear.
    work_entity_id: int | None = None
    # Preferred language (one of the workspace languages); empty = the workspace language.
    locale: str | None = Field(default=None, max_length=20)


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