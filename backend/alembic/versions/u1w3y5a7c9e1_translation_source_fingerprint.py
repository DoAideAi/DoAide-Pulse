"""content_translations.source_fingerprint — stale means the words changed

``is_stale`` compared ``content.version`` with the version a translation was
made from, but ``version`` is the optimistic lock and moves on every write:
approving, scheduling and publishing all bump it. A translation made of a draft
was therefore stale by the time the publish worker read it, and every
destination set to another language got English. This column holds a hash of
the words that were translated; staleness compares that instead. NULL — every
existing row — keeps the old version rule until it is next translated.

Revision ID: u1w3y5a7c9e1
Revises: t9v1x3z5b7d9
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'u1w3y5a7c9e1'
down_revision: str | None = 't9v1x3z5b7d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'content_translations',
        sa.Column('source_fingerprint', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('content_translations', 'source_fingerprint')
