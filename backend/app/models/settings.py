"""Application settings storage (organization profile, PDF export design).

Values live in a keyed JSON table so new settings categories can be added
without a schema change. Appearance preferences are per-user and live on the
users table instead, since they load on every authenticated request.
"""

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONType

ORG_SETTINGS_KEY = "org"
PDF_DESIGN_KEY = "pdf_design"


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_app_setting_key"),)

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
