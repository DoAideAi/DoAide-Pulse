"""seo_meta_audits table

The latest meta-tag audit of each DoAide site: titles, descriptions,
canonicals and Open Graph tags, per page and site-wide. See
:mod:`app.models.seo`.

Revision ID: h8j0e2g4i6k8
Revises: g7i9d1f3h5j7
Create Date: 2026-10-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'h8j0e2g4i6k8'
down_revision: str | None = 'g7i9d1f3h5j7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'seo_meta_audits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_key', sa.String(length=40), nullable=False),
        sa.Column('pages_scanned', sa.Integer(), nullable=False),
        sa.Column('issue_count', sa.Integer(), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_key'),
    )


def downgrade() -> None:
    op.drop_table('seo_meta_audits')
