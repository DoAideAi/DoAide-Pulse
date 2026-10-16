"""Add CHECK constraints to content_revisions and content_translations

Revision and word_count in content_revisions had no database-level guard against
negative or zero values.  content_translations.source_version likewise.  The
application layer prevented these, but a direct SQL write or a future code path
could have stored nonsense.

Revision ID: a1b2c3d4e5f7
Revises: z0t2p4r6s8o0
Create Date: 2026-10-11 01:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "z0t2p4r6s8o0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode: a plain ALTER on PostgreSQL, copy-and-move on SQLite, which
    # cannot add a constraint to an existing table. Without it the migration
    # chain could not be built on SQLite at all, and the test that diffs the
    # migrated schema against the models never got past this revision.
    with op.batch_alter_table("content_revisions") as batch:
        batch.create_check_constraint("ck_revision_positive", "revision > 0")
        batch.create_check_constraint("ck_revision_word_count_nonneg", "word_count >= 0")
    with op.batch_alter_table("content_translations") as batch:
        batch.create_check_constraint(
            "ck_translation_source_version_nonneg", "source_version >= 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("content_translations") as batch:
        batch.drop_constraint("ck_translation_source_version_nonneg", type_="check")
    with op.batch_alter_table("content_revisions") as batch:
        batch.drop_constraint("ck_revision_word_count_nonneg", type_="check")
        batch.drop_constraint("ck_revision_positive", type_="check")
