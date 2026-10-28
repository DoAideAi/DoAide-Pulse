"""Add the feedback table for the in-app feedback widget

Revision ID: n4p6r8t0v2x4
Revises: m3o5q7s9u1w3
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "n4p6r8t0v2x4"
down_revision: str | None = "m3o5q7s9u1w3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("page_url", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("detected_feature", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('bug', 'feature', 'general', 'other')", name="ck_feedback_category"
        ),
    )
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"])
    op.create_index("ix_feedback_category", "feedback", ["category"])
    op.create_index("ix_feedback_detected_feature", "feedback", ["detected_feature"])


def downgrade() -> None:
    op.drop_index("ix_feedback_detected_feature", table_name="feedback")
    op.drop_index("ix_feedback_category", table_name="feedback")
    op.drop_index("ix_feedback_created_at", table_name="feedback")
    op.drop_table("feedback")
