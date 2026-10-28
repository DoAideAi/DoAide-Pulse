"""subscribers: an address is unique per project, not across every account

``uq_subscriber_email`` made an address unique across the whole install. Lists
are counted per account through ``project_id``, so a reader already on one
account's list who signed up on another account's article was dropped as a
duplicate and never reached the second list. Existing rows already satisfy the
narrower constraint, so nothing has to be rewritten.

Revision ID: r7t9v1x3z5b7
Revises: q6s8u0w2y4a6
Create Date: 2026-10-29
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'r7t9v1x3z5b7'
down_revision: str | None = 'q6s8u0w2y4a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('subscribers') as batch:
        batch.drop_constraint('uq_subscriber_email', type_='unique')
        batch.create_unique_constraint(
            'uq_subscriber_email_project', ['email', 'project_id']
        )


def downgrade() -> None:
    # Keeps the earliest row for an address that is on several lists, which
    # is what the global constraint can hold.
    op.execute(
        "DELETE FROM subscribers WHERE id NOT IN "
        "(SELECT MIN(id) FROM subscribers GROUP BY email)"
    )
    with op.batch_alter_table('subscribers') as batch:
        batch.drop_constraint('uq_subscriber_email_project', type_='unique')
        batch.create_unique_constraint('uq_subscriber_email', ['email'])
