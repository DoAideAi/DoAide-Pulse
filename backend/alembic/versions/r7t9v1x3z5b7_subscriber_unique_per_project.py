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

import os
from collections.abc import Sequence

import sqlalchemy as sa

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


#: Set to ``1`` to let the downgrade delete the rows the global constraint
#: cannot hold. Without it a downgrade that would lose subscribers stops.
DROP_DUPLICATES_ENV = "PULSE_DOWNGRADE_DROP_DUPLICATE_SUBSCRIBERS"


def downgrade() -> None:
    # The global constraint can hold one row per address, so going back means
    # deleting every other list a reader is on — another account's audience,
    # gone as a side effect of a rollback. It used to do that silently. Now it
    # counts first and stops unless the operator has said that loss is wanted;
    # a rollback with nothing to lose (the usual case) is unaffected.
    duplicates = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM subscribers WHERE id NOT IN "
            "(SELECT MIN(id) FROM subscribers GROUP BY email)"
        )
    )
    if duplicates and os.environ.get(DROP_DUPLICATES_ENV) != "1":
        raise RuntimeError(
            f"Downgrading r7t9v1x3z5b7 would delete {duplicates} subscriber row(s): "
            "addresses on more than one project's list, which the old install-wide "
            "unique constraint cannot hold. Nothing was changed. Take a backup, then "
            f"re-run with {DROP_DUPLICATES_ENV}=1 to keep only the earliest row per "
            "address."
        )
    # Keeps the earliest row for an address that is on several lists, which
    # is what the global constraint can hold.
    op.execute(
        "DELETE FROM subscribers WHERE id NOT IN "
        "(SELECT MIN(id) FROM subscribers GROUP BY email)"
    )
    with op.batch_alter_table('subscribers') as batch:
        batch.drop_constraint('uq_subscriber_email_project', type_='unique')
        batch.create_unique_constraint('uq_subscriber_email', ['email'])
