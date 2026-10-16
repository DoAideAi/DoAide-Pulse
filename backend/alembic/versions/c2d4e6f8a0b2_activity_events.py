"""activity_events table

Page views and actions the browser reports for the signed-in user. See
:mod:`app.models.activity`. Bounded by the daily ``purge_old_activity`` tick on
the existing beat schedule rather than by a process of its own.

Revision ID: c2d4e6f8a0b2
Revises: b1c2d3e4f5a6
Create Date: 2026-10-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c2d4e6f8a0b2'
down_revision: str | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'activity_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('path', sa.String(length=300), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_activity_events_user_id'), 'activity_events', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_activity_events_created_at'),
        'activity_events',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_activity_events_created_at'), table_name='activity_events')
    op.drop_index(op.f('ix_activity_events_user_id'), table_name='activity_events')
    op.drop_table('activity_events')
