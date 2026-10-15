"""settings tables and user preferences

Revision ID: 7c1a9d3e5b40
Revises: 5ea882cfbadf
Create Date: 2026-10-15
"""
from typing import Sequence, Union

import app.db.types  # noqa: F401  (custom portable types referenced below)
from alembic import op
import sqlalchemy as sa

revision: str = '7c1a9d3e5b40'
down_revision: Union[str, None] = '5ea882cfbadf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
        sa.Column('updated_at', app.db.types.UTCDateTime(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', app.db.types.JSONType(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='uq_app_setting_key'),
    )
    op.add_column('users', sa.Column('preferences', app.db.types.JSONType(), nullable=False,
                                     server_default='{}'))


def downgrade() -> None:
    op.drop_column('users', 'preferences')
    op.drop_table('app_settings')
