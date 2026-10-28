"""users.digest_sent_at — the weekly digest is sent at most once a week

The sweep had no record of whom it had already mailed. Celery acks the task
late, so a worker killed mid-sweep had it redelivered, and a sweep outliving
the broker's visibility timeout ran twice at once: every user already reached
got the same digest again. The sweep now claims this column per user before
sending. NULL — every existing row — means "never sent", so nobody is skipped
on the first Monday after deploy.

Revision ID: s8u0w2y4a6c8
Revises: r7t9v1x3z5b7
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 's8u0w2y4a6c8'
down_revision: str | None = 'r7t9v1x3z5b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('digest_sent_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'digest_sent_at')
