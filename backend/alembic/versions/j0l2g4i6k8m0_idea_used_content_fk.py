"""content_ideas.used_content_id becomes a foreign key, ON DELETE SET NULL

The column marked an idea as written by holding the draft's id, with no
constraint behind it, on the reasoning that an idea must outlive a draft the
user deletes. It did outlive it — invisibly. Every list of ideas (the calendar,
a project's ideas, the generator's "not yet used" filter) selects
``used_content_id IS NULL``, so an idea whose draft was deleted kept a dangling
id and dropped out of all of them for good, while the machine API went on
reporting it as "used". The write endpoint already treats a missing draft as
"write it again"; nothing could reach the idea to ask.

SET NULL is the behaviour the comment wanted: the idea survives the delete, and
goes back to being an unwritten idea. Existing dangling ids are cleared first,
or the constraint could not be created over them.

Revision ID: j0l2g4i6k8m0
Revises: i9k1f3h5j7l9
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'j0l2g4i6k8m0'
down_revision: str | None = 'i9k1f3h5j7l9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = 'fk_content_ideas_used_content_id_content'


def upgrade() -> None:
    op.execute(
        "UPDATE content_ideas SET used_content_id = NULL "
        "WHERE used_content_id IS NOT NULL "
        "AND used_content_id NOT IN (SELECT id FROM content)"
    )
    with op.batch_alter_table('content_ideas', schema=None) as batch_op:
        batch_op.create_foreign_key(
            FK_NAME, 'content', ['used_content_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    # The ids cleared on the way up pointed at drafts that no longer exist;
    # there is nothing to put back.
    with op.batch_alter_table('content_ideas', schema=None) as batch_op:
        batch_op.drop_constraint(FK_NAME, type_='foreignkey')
