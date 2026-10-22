"""SEO health history, sitemap run log, and planned content ideas

Three pieces of one improvement:

* ``seo_health_snapshots`` — one row per day of estate-wide SEO totals, so the
  dashboard can chart health over time instead of only showing the latest state.
* ``seo_sitemap_runs`` — one row per sitemap submission sweep (scheduled or
  manual), the status page for the automated weekly submission.
* ``content_ideas.planned_date`` — an idea can be planned onto a calendar day
  before anyone writes it.

Revision ID: i9k1f3h5j7l9
Revises: h8j0e2g4i6k8
Create Date: 2026-10-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'i9k1f3h5j7l9'
down_revision: str | None = 'h8j0e2g4i6k8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'seo_health_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('sites', sa.Integer(), nullable=False),
        sa.Column('sitemaps_submitted', sa.Integer(), nullable=False),
        sa.Column('sitemap_problems', sa.Integer(), nullable=False),
        sa.Column('urls_in_sitemaps', sa.Integer(), nullable=False),
        sa.Column('indexed_pages', sa.Integer(), nullable=False),
        sa.Column('meta_issues', sa.Integer(), nullable=False),
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
        sa.UniqueConstraint('snapshot_date'),
    )
    op.create_table(
        'seo_sitemap_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trigger', sa.String(length=20), nullable=False),
        sa.Column('sites_checked', sa.Integer(), nullable=False),
        sa.Column('sites_submitted', sa.Integer(), nullable=False),
        sa.Column('problems', sa.JSON(), nullable=False),
        sa.Column('ran_at', sa.DateTime(timezone=True), nullable=False),
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
    )
    op.create_index('ix_seo_sitemap_runs_ran_at', 'seo_sitemap_runs', ['ran_at'])
    op.add_column('content_ideas', sa.Column('planned_date', sa.Date(), nullable=True))
    op.create_index('ix_content_ideas_planned_date', 'content_ideas', ['planned_date'])


def downgrade() -> None:
    op.drop_index('ix_content_ideas_planned_date', table_name='content_ideas')
    op.drop_column('content_ideas', 'planned_date')
    op.drop_index('ix_seo_sitemap_runs_ran_at', table_name='seo_sitemap_runs')
    op.drop_table('seo_sitemap_runs')
    op.drop_table('seo_health_snapshots')
