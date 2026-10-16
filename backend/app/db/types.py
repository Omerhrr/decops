"""Portable custom types for cross-database compatibility (PostgreSQL <-> SQLite)."""

from datetime import UTC

from sqlalchemy import types
from sqlalchemy.dialects.postgresql import JSONB


class JSONType(types.TypeDecorator):
    """JSON that maps to JSONB on PostgreSQL (indexable) and JSON elsewhere."""

    impl = types.JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(types.JSON())

    def __repr__(self) -> str:  # alembic renders module prefix + this repr
        return "JSONType()"


class UTCDateTime(types.TypeDecorator):
    """DateTime that always stores and returns timezone-aware UTC values
    ."""

    impl = types.DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        return dialect.type_descriptor(types.DateTime(timezone=True))

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            value = value.astimezone(UTC)
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def __repr__(self) -> str:
        return "UTCDateTime()"
