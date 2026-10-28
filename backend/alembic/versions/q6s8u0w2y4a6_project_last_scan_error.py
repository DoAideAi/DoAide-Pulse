"""projects.last_scan_error — why the last scan could not read the repo

A scan that reached GitHub and was refused (a renamed, deleted or private repo)
still advanced ``scan_count`` and ``last_scanned_at``, so on /api/v1/metrics it
looked exactly like a project being scanned on schedule. The reason is now kept
beside the counters and cleared by the next scan that reads the repo.

Revision ID: q6s8u0w2y4a6
Revises: p5r7t9v1x3z5
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'q6s8u0w2y4a6'
down_revision: str | None = 'p5r7t9v1x3z5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('last_scan_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'last_scan_error')
