"""trigger_events.content_id becomes a foreign key, ON DELETE SET NULL

The column recorded which piece a trigger firing wrote, with no constraint
behind it, on the reasoning that an event is a log entry and must outlive a
draft the user deletes. It did outlive it — with a dangling id, which the
trigger activity list renders as a "View piece" link to a 404. The precedent
the model cited, ``content_ideas.used_content_id``, has been a SET NULL foreign
key since j0l2g4i6k8m0 for the same reason.

SET NULL keeps the event and drops the reference with the piece. Existing
dangling ids are cleared first, or the constraint could not be created over
them; the index is what keeps the SET NULL from scanning every event per
deleted piece.

Revision ID: p5r7t9v1x3z5
Revises: n4p6r8t0v2x4
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'p5r7t9v1x3z5'
down_revision: str | None = 'n4p6r8t0v2x4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = 'fk_trigger_events_content_id_content'
INDEX_NAME = 'ix_trigger_events_content_id'


def upgrade() -> None:
    op.execute(
        "UPDATE trigger_events SET content_id = NULL "
        "WHERE content_id IS NOT NULL "
        "AND content_id NOT IN (SELECT id FROM content)"
    )
    with op.batch_alter_table('trigger_events', schema=None) as batch_op:
        batch_op.create_index(INDEX_NAME, ['content_id'])
        batch_op.create_foreign_key(
            FK_NAME, 'content', ['content_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    # The ids cleared on the way up pointed at pieces that no longer exist;
    # there is nothing to put back.
    with op.batch_alter_table('trigger_events', schema=None) as batch_op:
        batch_op.drop_constraint(FK_NAME, type_='foreignkey')
        batch_op.drop_index(INDEX_NAME)
