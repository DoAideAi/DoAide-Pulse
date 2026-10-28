"""Index content_ideas.used_content_id

``j0l2g4i6k8m0`` made the column a foreign key with ON DELETE SET NULL and
built no index under it. PostgreSQL does not index a referencing column on its
own, so every draft deleted made the database scan ``content_ideas`` for the
ideas pointing at it — once per row, on a bulk delete — and every idea list's
``used_content_id IS NULL`` filter read the table too.

Revision ID: k1m3h5j7l9n1
Revises: j0l2g4i6k8m0
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'k1m3h5j7l9n1'
down_revision: str | None = 'j0l2g4i6k8m0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        'ix_content_ideas_used_content_id', 'content_ideas', ['used_content_id']
    )


def downgrade() -> None:
    op.drop_index('ix_content_ideas_used_content_id', table_name='content_ideas')
