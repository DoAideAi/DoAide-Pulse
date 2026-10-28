"""activity_events (user_id, created_at) index; CHECKs on three closed string columns

The activity summary reads one user's rows inside a time window, and the table
had only separate single-column indexes on ``user_id`` and ``created_at`` — so
the planner used one and filtered the other.

``activity_events.kind``, ``product_events.kind`` and
``seo_sitemaps.submit_status`` each hold one of a small fixed set of values,
enforced by the API schema and nothing else. A CHECK makes the database say the
same thing. Every existing row was written through that schema, so none fails it.

Revision ID: m3o5q7s9u1w3
Revises: k1m3h5j7l9n1
Create Date: 2026-10-28 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "m3o5q7s9u1w3"
down_revision: str | None = "k1m3h5j7l9n1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_activity_events_user_created", "activity_events", ["user_id", "created_at"]
    )
    # Batch mode for SQLite, which cannot add a constraint to an existing table;
    # see a1b2c3d4e5f7.
    with op.batch_alter_table("activity_events") as batch:
        batch.create_check_constraint(
            "ck_activity_event_kind", "kind IN ('page_view', 'action')"
        )
    with op.batch_alter_table("product_events") as batch:
        batch.create_check_constraint(
            "ck_product_event_kind", "kind IN ('signup', 'login', 'action')"
        )
    with op.batch_alter_table("seo_sitemaps") as batch:
        batch.create_check_constraint(
            "ck_sitemap_submit_status",
            "submit_status IN ('submitted', 'error', 'unconfigured')",
        )


def downgrade() -> None:
    with op.batch_alter_table("seo_sitemaps") as batch:
        batch.drop_constraint("ck_sitemap_submit_status", type_="check")
    with op.batch_alter_table("product_events") as batch:
        batch.drop_constraint("ck_product_event_kind", type_="check")
    with op.batch_alter_table("activity_events") as batch:
        batch.drop_constraint("ck_activity_event_kind", type_="check")
    op.drop_index("ix_activity_events_user_created", table_name="activity_events")
