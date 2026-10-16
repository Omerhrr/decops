""" administration schemas: users, departments, RBAC."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AccountStatus, DepartmentStatus, MembershipRole
from app.schemas.common import RoleBrief


# ---------- Users: create / update / detail ----------
class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    employee_code: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=10, max_length=200)
    role_ids: list[uuid.UUID] = []


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None


class UserStatusRequest(BaseModel):
    status: AccountStatus
    reason: str | None = Field(None, max_length=500)


class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: uuid.UUID
    user_id: uuid.UUID
    membership_role: MembershipRole
    valid_from: date | None = None
    valid_until: date | None = None


class UserDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    email: EmailStr
    account_status: AccountStatus
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[RoleBrief] = []
    memberships: list[MembershipOut] = []


# ---------- Roles & permissions ----------
class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    is_system_role: bool
    permissions: list[str] = []


class RoleWriteRequest(BaseModel):
    # Optional so PATCH can send partial updates; POST requires it explicitly.
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] | None = None


class RoleAssignRequest(BaseModel):
    role_id: uuid.UUID


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str | None = None


class RoleListPage(BaseModel):
    items: list[RoleOut]
    total: int


class PermissionListPage(BaseModel):
    items: list[PermissionOut]
    total: int


# ---------- Departments ----------
class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    lead_user_id: uuid.UUID | None = None


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    status: DepartmentStatus | None = None
    lead_user_id: uuid.UUID | None = None


class DepartmentMemberAddRequest(BaseModel):
    user_id: uuid.UUID
    membership_role: MembershipRole = MembershipRole.member
    valid_from: date | None = None
    valid_until: date | None = None


class DepartmentMemberUserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    employee_code: str
    account_status: AccountStatus


class DepartmentMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    membership_role: MembershipRole
    valid_from: date | None = None
    valid_until: date | None = None
    user: DepartmentMemberUserBrief | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    status: DepartmentStatus
    lead_user_id: uuid.UUID | None = None
    lead: DepartmentMemberUserBrief | None = None
    member_count: int = 0


class DepartmentDetailOut(DepartmentOut):
    memberships: list[DepartmentMembershipOut] = []
