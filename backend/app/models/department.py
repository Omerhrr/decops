"""Department models (spec data_model: departments, department_memberships)."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.types import UTCDateTime


class DepartmentStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    department_lead_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[DepartmentStatus] = mapped_column(
        String(20), default=DepartmentStatus.active, nullable=False
    )

    memberships = relationship(
        "DepartmentMembership", back_populates="department", lazy="selectin"
    )


class MembershipRole(str, enum.Enum):
    lead = "lead"
    member = "member"


class DepartmentMembership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "department_memberships"
    __table_args__ = (
        UniqueConstraint("department_id", "user_id", name="uq_department_membership"),
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    membership_role: Mapped[MembershipRole] = mapped_column(
        String(20), default=MembershipRole.member, nullable=False
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    department = relationship("Department", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
