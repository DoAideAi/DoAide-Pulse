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


#: How many times a new piece is offered to the database before giving up.
#: One retry was the old budget, and the second collision — or any integrity
#: error that was not a collision at all — escaped as a 500 after a retry that
#: could not have helped.
MAX_ATTEMPTS = 3

_SLUG_CONSTRAINT = "uq_content_project_slug"


def is_slug_collision(exc: IntegrityError) -> bool:
    """Whether *exc* is the (project, slug) unique constraint and nothing else.

    PostgreSQL names the constraint, on ``diag`` and in the message; SQLite
    names the columns. Anything else — a foreign key to a project deleted in
    another tab, a CHECK — is not fixed by a new slug, and retrying it only
    doubles the work before the same failure.
    """
    orig = getattr(exc, "orig", None)
    name = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if name:
        return name == _SLUG_CONSTRAINT
    text = str(orig if orig is not None else exc)
    return _SLUG_CONSTRAINT in text or "content.project_id, content.slug" in text


def commit_new(db: Session, content: Content) -> None:
    """Add and commit, retrying on a slug collision.

    ``unique_content_slug`` prevents most collisions, but two concurrent
    requests can race past the check. The database-level unique constraint
    catches the loser; we regenerate the slug and retry rather than surfacing a
    500. The retry appends random hex rather than re-running the count query,
    which would be open to the same race a second time.

    Only the slug constraint is retried, at most :data:`MAX_ATTEMPTS` times in
    all, each from the original stem so a retried slug never grows two
    suffixes. Any other integrity error is re-raised on the first attempt.
    """
    stem = content.slug
    for attempt in range(1, MAX_ATTEMPTS + 1):
        db.add(content)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if attempt == MAX_ATTEMPTS or not is_slug_collision(exc):
                raise
            content.slug = f"{stem}-{secrets.token_hex(3)}"
        else:
            break
    db.refresh(content)


__all__ = ["MAX_ATTEMPTS", "commit_new", "is_slug_collision"]
