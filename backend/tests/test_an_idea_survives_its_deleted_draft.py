"""Deleting a draft returns the idea it came from to the backlog.

``content_ideas.used_content_id`` held the draft's id with no constraint, and
every idea list filters on it being null — so an idea whose draft was deleted
kept a dangling id and vanished from the calendar, the project's idea list and
the generator's pool for good. It is a foreign key with ON DELETE SET NULL now.

The suite's own engine is SQLite without ``PRAGMA foreign_keys``, which ignores
every foreign key, so this builds one that enforces them. PostgreSQL always
does.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.content import Content, ContentIdea, ContentType
from app.models.project import Project, Tone
from app.models.user import User


def _engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def test_deleting_the_draft_puts_the_idea_back():
    engine = _engine()
    with Session(engine) as db:
        user = User(email="fk@example.com", hashed_password="x")
        db.add(user)
        db.flush()
        project = Project(
            user_id=user.id, name="P", slug="p", description="d", tone=Tone.TECHNICAL
        )
        db.add(project)
        db.flush()
        draft = Content(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            title="Written",
            slug="written",
            body_markdown="Body.",
        )
        db.add(draft)
        db.flush()
        idea = ContentIdea(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            headline="An idea",
            used_content_id=draft.id,
        )
        db.add(idea)
        db.commit()
        idea_id = idea.id

        db.delete(draft)
        db.commit()
        db.expire_all()

        assert db.get(ContentIdea, idea_id).used_content_id is None
        unused = db.scalars(
            select(ContentIdea.id).where(ContentIdea.used_content_id.is_(None))
        ).all()
        assert idea_id in unused
    engine.dispose()
