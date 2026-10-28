"""projects.scan_claimed_at — one scan of a project at a time

A scan reads the watermark, generates a piece and only then moves it. Two scans
in that window — a late-acked task redelivered, a sweep re-dispatching a
project whose scan is still queued, the Scan button beside either — each wrote
the same post. A scan now takes this column as a lease before reading GitHub.
NULL — every existing row — means nothing is scanning it.

Revision ID: t9v1x3z5b7d9
Revises: s8u0w2y4a6c8
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 't9v1x3z5b7d9'
down_revision: str | None = 's8u0w2y4a6c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'projects', sa.Column('scan_claimed_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('projects', 'scan_claimed_at')
