"""``/articles/{slug}`` answers with the same piece every time.

Slugs are unique per project, so two accounts can each publish
``hello-world``. The lookup was unordered: which one a shared link showed was
the planner's choice, and a newer piece by a stranger could take it over.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.user import User
from app.security import hash_password


def _piece(db, project, *, title, published_days_ago):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.PUBLISHED,
        title=title,
        slug="hello-world",
        body_markdown="Body.",
        published_at=utcnow() - timedelta(days=published_days_ago),
    )
    db.add(row)
    db.commit()
    return row


def test_the_first_published_piece_keeps_the_slug(client, db, project):
    stranger = User(
        email="stranger@example.com", full_name="S", hashed_password=hash_password("x" * 12)
    )
    db.add(stranger)
    db.commit()
    theirs = Project(user_id=stranger.id, name="Theirs", slug="theirs", description="d")
    db.add(theirs)
    db.commit()

    # The stranger's row is inserted first but published later.
    _piece(db, theirs, title="Newer, someone else's", published_days_ago=1)
    _piece(db, project, title="The original", published_days_ago=90)

    for _ in range(3):
        resp = client.get("/api/v1/articles/hello-world")
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "The original"
