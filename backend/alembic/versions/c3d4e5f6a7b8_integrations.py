"""api tokens, webhooks, recurring tasks

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import app.db.types  # noqa: F401
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base():
    return [
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
        sa.Column('updated_at', app.db.types.UTCDateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        'api_tokens',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=12), nullable=False),
        sa.Column('scope', sa.String(length=10), nullable=False),
        sa.Column('expires_at', app.db.types.UTCDateTime(), nullable=True),
        sa.Column('last_used_at', app.db.types.UTCDateTime(), nullable=True),
        sa.Column('revoked_at', app.db.types.UTCDateTime(), nullable=True),
        *_base(),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'])
    op.create_index('ix_api_tokens_token_hash', 'api_tokens', ['token_hash'], unique=True)
    op.create_table(
        'webhooks',
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('secret_enc', sa.Text(), nullable=False),
        sa.Column('events', app.db.types.JSONType(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_by_id', sa.Uuid(), nullable=True),
        sa.Column('last_status', sa.String(length=200), nullable=True),
        sa.Column('last_delivery_at', app.db.types.UTCDateTime(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False),
        *_base(),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'recurring_tasks',
        sa.Column('created_by_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('accountable_pm_id', sa.Uuid(), nullable=False),
        sa.Column('visibility_mode', sa.String(length=30), nullable=False),
        sa.Column('department_ids', app.db.types.JSONType(), nullable=False),
        sa.Column('frequency', sa.String(length=10), nullable=False),
        sa.Column('interval', sa.Integer(), nullable=False),
        sa.Column('due_after_days', sa.Integer(), nullable=False),
        sa.Column('next_run_on', sa.Date(), nullable=False),
        sa.Column('last_run_at', app.db.types.UTCDateTime(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('last_error', sa.String(length=300), nullable=True),
        *_base(),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['accountable_pm_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recurring_tasks_created_by_id', 'recurring_tasks', ['created_by_id'])


def downgrade() -> None:
    op.drop_index('ix_recurring_tasks_created_by_id', table_name='recurring_tasks')
    op.drop_table('recurring_tasks')
    op.drop_table('webhooks')
    op.drop_index('ix_api_tokens_token_hash', table_name='api_tokens')
    op.drop_index('ix_api_tokens_user_id', table_name='api_tokens')
    op.drop_table('api_tokens')
