"""saved filters

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import app.db.types  # noqa: F401
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_filters',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('params', app.db.types.JSONType(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
        sa.Column('updated_at', app.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_saved_filters_user_name'),
    )
    op.create_index('ix_saved_filters_user_id', 'saved_filters', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_saved_filters_user_id', table_name='saved_filters')
    op.drop_table('saved_filters')
