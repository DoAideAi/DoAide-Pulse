"""seo_sitemaps table

Where each DoAide site's sitemap stands: fetched and counted by Pulse, and
submitted to Search Console. See :mod:`app.models.seo`.

Revision ID: g7i9d1f3h5j7
Revises: f6h8c0e2g4i6
Create Date: 2026-10-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'g7i9d1f3h5j7'
down_revision: str | None = 'f6h8c0e2g4i6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'seo_sitemaps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_key', sa.String(length=40), nullable=False),
        sa.Column('sitemap_url', sa.String(length=500), nullable=False),
        sa.Column('url_count', sa.Integer(), nullable=True),
        sa.Column('fetch_error', sa.Text(), nullable=True),
        sa.Column('submit_status', sa.String(length=20), nullable=False),
        sa.Column('submit_error', sa.Text(), nullable=True),
        sa.Column('gsc_submitted', sa.Integer(), nullable=True),
        sa.Column('gsc_indexed', sa.Integer(), nullable=True),
        sa.Column('gsc_errors', sa.Integer(), nullable=True),
        sa.Column('gsc_warnings', sa.Integer(), nullable=True),
        sa.Column('gsc_last_downloaded', sa.String(length=40), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
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
    op.drop_table('seo_sitemaps')
