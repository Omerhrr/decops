"""RBAC models (spec data_model: roles, permissions, role_permissions, user_roles)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.db.types import UTCDateTime


class Role(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_system_role: Mapped[bool] = mapped_column(default=False, nullable=False)

    permissions = relationship(
        "RolePermission", back_populates="role", lazy="selectin", cascade="all, delete-orphan"
    )


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    role_links = relationship(
        "RolePermission", back_populates="permission", lazy="selectin",
        cascade="all, delete-orphan",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="role_links")


class ScopeType(str):
    """Scope of a role assignment. Kept as plain strings for extensibility."""

    GLOBAL = "global"
    DEPARTMENT = "department"
    TASK = "task"


class UserRole(UUIDPrimaryKeyMixin, Base):
    """A role granted to a user, optionally scoped (global / department / task)."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "scope_type", "scope_id",
                                       name="uq_user_role_scope"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(20), default=ScopeType.GLOBAL, nullable=False)
    # NULL for global scope; department/user/task id for scoped roles
    scope_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user = relationship("User", back_populates="roles", foreign_keys=[user_id])
    role = relationship("Role", lazy="joined")
