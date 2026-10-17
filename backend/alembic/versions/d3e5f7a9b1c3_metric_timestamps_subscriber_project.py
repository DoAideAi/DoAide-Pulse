"""content_metrics timestamps and subscribers.project_id

c59bd32 gave ``ContentMetric`` the ``TimestampMixin`` and ``Subscriber`` a
``project_id`` and wrote no migration for either. Every query that loads a
metric row names ``content_metrics.created_at``, so the dashboard, the
analytics endpoints, the platform-reach panel and the metrics poll all 500'd
against a database that had never heard of the column.

Existing snapshots take ``captured_at`` as their creation time — it is the
moment the row was written, which is what ``created_at`` means. The columns are
added nullable, backfilled, then tightened, because SQLite cannot add a NOT NULL
column with a non-constant default in one step.

Revision ID: d3e5f7a9b1c3
Revises: c2d4e6f8a0b2
Create Date: 2026-10-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd3e5f7a9b1c3'
down_revision: str | None = 'c2d4e6f8a0b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'content_metrics', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'content_metrics', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE content_metrics SET created_at = captured_at, updated_at = captured_at"
    )
    with op.batch_alter_table('content_metrics') as batch:
        batch.alter_column(
            'created_at',
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            'updated_at',
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )

    with op.batch_alter_table('subscribers') as batch:
        batch.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch.create_index('ix_subscribers_project_id', ['project_id'])
        batch.create_foreign_key(
            'fk_subscribers_project_id_projects',
            'projects',
            ['project_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('subscribers') as batch:
        batch.drop_constraint('fk_subscribers_project_id_projects', type_='foreignkey')
        batch.drop_index('ix_subscribers_project_id')
        batch.drop_column('project_id')
    with op.batch_alter_table('content_metrics') as batch:
        batch.drop_column('updated_at')
        batch.drop_column('created_at')
