"""An index on product_events (kind, occurred_at) for the recent signups panel

``product_activity.recent`` reads the newest signups and logins across every
product. With only ``occurred_at`` indexed, PostgreSQL walked events newest
first and discarded every ``action`` — most of the 90 days kept — until twenty
of the rare kinds had gone by, on every load of the products dashboard.

Revision ID: w3y5a7c9e1g3
Revises: v2x4z6b8d0f2
Create Date: 2026-10-30
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "w3y5a7c9e1g3"
down_revision: str | None = "v2x4z6b8d0f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_product_events_kind_occurred", "product_events", ["kind", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_events_kind_occurred", table_name="product_events")
