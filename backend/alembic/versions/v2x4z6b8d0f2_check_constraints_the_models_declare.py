"""The 24 CHECK constraints the models declare and no migration ever created

Every test runs on ``Base.metadata.create_all``, so every test had them; the
deployed database is built by this chain and had none of them. Code leans on
them — ``publishing_service._count`` documents that a negative count "trips the
column's >= 0 check" — and on PostgreSQL there was nothing to trip.

Adding a CHECK on PostgreSQL validates every existing row, and one stray
negative would fail the deploy part way. So each column is repaired first,
to the nearest value the constraint allows: a negative count to 0, a
confidence outside 0..1 to its bound. NULLs pass every one of these as they
are. Batch mode, so the chain still builds on SQLite.

Revision ID: v2x4z6b8d0f2
Revises: u1w3y5a7c9e1
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "v2x4z6b8d0f2"
down_revision: str | None = "u1w3y5a7c9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, constraint, condition, column) — the condition exactly as the model
#: declares it; the column is the one a stray value is repaired in.
_NONNEG: tuple[tuple[str, str, str, str], ...] = (
    ("content", "ck_content_word_count_nonneg", "word_count >= 0", "word_count"),
    ("llm_usage", "ck_llm_usage_completion_tokens_nonneg",
     "completion_tokens IS NULL OR completion_tokens >= 0", "completion_tokens"),
    ("llm_usage", "ck_llm_usage_prompt_tokens_nonneg",
     "prompt_tokens IS NULL OR prompt_tokens >= 0", "prompt_tokens"),
    ("llm_usage", "ck_llm_usage_total_tokens_nonneg",
     "total_tokens IS NULL OR total_tokens >= 0", "total_tokens"),
    ("llm_usage", "ck_llm_usage_duration_nonneg", "duration_ms >= 0", "duration_ms"),
    ("content_metrics", "ck_metric_comments_nonneg", "comments IS NULL OR comments >= 0",
     "comments"),
    ("content_metrics", "ck_metric_reactions_nonneg", "reactions IS NULL OR reactions >= 0",
     "reactions"),
    ("content_metrics", "ck_metric_shares_nonneg", "shares IS NULL OR shares >= 0", "shares"),
    ("content_metrics", "ck_metric_reads_nonneg", "reads IS NULL OR reads >= 0", "reads"),
    ("content_metrics", "ck_metric_clicks_nonneg", "clicks IS NULL OR clicks >= 0", "clicks"),
    ("content_metrics", "ck_metric_views_nonneg", "views IS NULL OR views >= 0", "views"),
    ("publications", "ck_publication_duration_nonneg",
     "duration_ms IS NULL OR duration_ms >= 0", "duration_ms"),
    ("publications", "ck_publication_attempts_nonneg", "attempts >= 0", "attempts"),
    ("preview_links", "ck_preview_link_view_count_nonneg", "view_count >= 0", "view_count"),
    ("projects", "ck_project_scan_count_nonneg", "scan_count >= 0", "scan_count"),
    ("projects", "ck_project_scan_duration_nonneg",
     "last_scan_duration_ms IS NULL OR last_scan_duration_ms >= 0", "last_scan_duration_ms"),
    ("projects", "ck_project_min_interval_nonneg", "autopilot_min_interval_hours >= 0",
     "autopilot_min_interval_hours"),
    ("projects", "ck_project_engagement_threshold_nonneg", "engagement_threshold >= 0",
     "engagement_threshold"),
    ("content_templates", "ck_template_use_count_nonneg", "use_count >= 0", "use_count"),
    ("triggers", "ck_trigger_failures_nonneg", "consecutive_failures >= 0",
     "consecutive_failures"),
    ("triggers", "ck_trigger_fire_count_nonneg", "fire_count >= 0", "fire_count"),
    ("webhooks", "ck_webhook_failures_nonneg", "consecutive_failures >= 0",
     "consecutive_failures"),
    ("webhook_deliveries", "ck_delivery_attempts_nonneg", "attempts >= 0", "attempts"),
)

_CONFIDENCE = (
    "content",
    "ck_content_confidence_range",
    "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
)


def _tables() -> list[str]:
    return sorted({table for table, *_ in _NONNEG} | {_CONFIDENCE[0]})


def upgrade() -> None:
    # Repair first: an ADD CONSTRAINT that meets one violating row fails.
    for table, _name, _condition, column in _NONNEG:
        op.execute(sa.text(f"UPDATE {table} SET {column} = 0 WHERE {column} < 0"))
    op.execute(sa.text("UPDATE content SET confidence = 0 WHERE confidence < 0"))
    op.execute(sa.text("UPDATE content SET confidence = 1 WHERE confidence > 1"))

    for table in _tables():
        with op.batch_alter_table(table) as batch:
            for owner, name, condition, _column in _NONNEG:
                if owner == table:
                    batch.create_check_constraint(name, condition)
            if table == _CONFIDENCE[0]:
                batch.create_check_constraint(_CONFIDENCE[1], _CONFIDENCE[2])


def downgrade() -> None:
    for table in _tables():
        with op.batch_alter_table(table) as batch:
            if table == _CONFIDENCE[0]:
                batch.drop_constraint(_CONFIDENCE[1], type_="check")
            for owner, name, _condition, _column in reversed(_NONNEG):
                if owner == table:
                    batch.drop_constraint(name, type_="check")
