"""User and session models (spec data_model: users; sessions for MOD-001)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.types import JSONType, UTCDateTime


class AccountStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    deactivated = "deactivated"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Spec calls this authentication_reference; for locally managed credentials it
    # holds the Argon2id hash of the password. SSO reference will reuse this column.
    authentication_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_status: Mapped[AccountStatus] = mapped_column(
        String(20), default=AccountStatus.active, nullable=False, index=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # Login throttling state (SEC-001)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Appearance preferences (theme mode, accent color, font). JSON so the
    # set of tunable keys can grow without migrations.
    preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    memberships = relationship(
        "DepartmentMembership", back_populates="user", lazy="selectin"
    )
    roles = relationship(
        "UserRole", back_populates="user", lazy="selectin",
        foreign_keys="UserRole.user_id",
    )

    @property
    def is_active(self) -> bool:
        return self.account_status == AccountStatus.active

    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()


class UserSession(UUIDPrimaryKeyMixin, Base):
    """Server-managed session (spec authentication: secure HttpOnly cookie sessions,
    expiration and revocation). Only the token hash is persisted."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")

    @property
    def is_usable(self) -> bool:
        now = utcnow()
        return self.revoked_at is None and self.expires_at > now
