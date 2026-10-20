"""product_events table

Signups, logins and key actions reported by the other DoAide products, for the
cross-product dashboard. See :mod:`app.models.product_event`.

Revision ID: f6h8c0e2g4i6
Revises: e5g7b9d1f3h5
Create Date: 2026-10-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'f6h8c0e2g4i6'
down_revision: str | None = 'e5g7b9d1f3h5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'product_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product', sa.String(length=40), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('actor', sa.String(length=120), nullable=True),
        sa.Column(
            'occurred_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_product_events_occurred_at'), 'product_events', ['occurred_at'], unique=False
    )
    op.create_index(
        'ix_product_events_product_occurred',
        'product_events',
        ['product', 'occurred_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_product_events_product_occurred', table_name='product_events')
    op.drop_index(op.f('ix_product_events_occurred_at'), table_name='product_events')
    op.drop_table('product_events')
