"""Pydantic request/response schemas (strict validation, conventions)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AccountStatus


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    employee_code: str


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    email: EmailStr
    account_status: AccountStatus
    last_login_at: datetime | None = None
    roles: list[RoleBrief] = []
    permissions: list[str] = []
    preferences: dict = {}


class AuthErrorResponse(BaseModel):
    error: dict


# ---------- Users (admin list - expands) ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    email: EmailStr
    account_status: AccountStatus
    last_login_at: datetime | None = None
    created_at: datetime


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


# ---------- Health ----------
class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str
    database: str
