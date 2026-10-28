"""Writing a new piece to the database.

The slug-collision retry used to live in the content router as a private
helper that the templates router also imported. It is persistence, not
presentation, so it belongs with the services that the routers call.
"""
from __future__ import annotations

import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.content import Content


def commit_new(db: Session, content: Content) -> None:
    """Add and commit, retrying once on a slug collision.

    ``unique_content_slug`` prevents most collisions, but two concurrent
    requests can race past the check. The database-level unique constraint
    catches the loser; we regenerate the slug and retry rather than surfacing a
    500. The retry appends random hex rather than re-running the count query,
    which would be open to the same race a second time.
    """
    db.add(content)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        content.slug = f"{content.slug}-{secrets.token_hex(3)}"
        db.add(content)
        db.commit()
    db.refresh(content)


__all__ = ["commit_new"]
