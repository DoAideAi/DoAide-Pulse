"""user_llm_keys: a user's own LLM API key

Revision ID: e5g7b9d1f3h5
Revises: d3e5f7a9b1c3
Create Date: 2026-10-18 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5g7b9d1f3h5'
down_revision: str | None = 'd3e5f7a9b1c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_llm_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('model', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('encrypted_key', sa.Text(), nullable=False, server_default=''),
        sa.Column('key_hint', sa.String(length=12), nullable=False, server_default=''),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index('ix_user_llm_keys_user_id', 'user_llm_keys', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_user_llm_keys_user_id', table_name='user_llm_keys')
    op.drop_table('user_llm_keys')
