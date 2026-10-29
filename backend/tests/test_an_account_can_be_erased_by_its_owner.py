"""An account holder can erase their account and everything in it.

There was no way to: deactivation is an operator's action and keeps every row.
``DELETE /auth/me`` asks for the password again and then deletes the user, and
the database cascades the rest. The cascade test builds an engine that enforces
foreign keys — the suite's SQLite engine does not, and PostgreSQL always does —
so it proves the rows really go, rather than that nothing complained.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.api_key import ApiKey
from app.models.content import Content, ContentType
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.project import Project, Tone
from app.models.publication import Platform
from app.models.revision import ContentRevision
from app.models.subscriber import Subscriber
from app.models.user import User
from app.models.webhook import Webhook
from app.services import accounts

ME = "/api/v1/auth/me"


def _engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _account(db: Session, email: str) -> tuple[User, Project]:
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.flush()
    project = Project(user_id=user.id, name=email, slug=email.split("@")[0], description="d", tone=Tone.TECHNICAL)
    db.add(project)
    db.flush()
    piece = Content(project_id=project.id, content_type=ContentType.TUTORIAL, title="T", slug="t", body_markdown="B")
    db.add(piece)
    db.flush()
    db.add_all(
        [
            ContentRevision(content_id=piece.id, revision=1, title="T", body_markdown="old", author_user_id=user.id),
            PlatformConnection(
                user_id=user.id,
                platform=Platform.DEVTO,
                status=ConnectionStatus.CONNECTED,
                encrypted_credentials="ciphertext",
            ),
            Webhook(user_id=user.id, url="https://hooks.example.com/x", events=["content.published"], encrypted_secret="s"),
            Subscriber(email=f"reader-of-{email}", project_id=project.id),
        ]
    )
    db.flush()
    return user, project


def _count(db: Session, model, **where) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return db.scalar(query) or 0


def test_erasing_takes_everything_the_account_owns_and_nothing_else():
    engine = _engine()
    with Session(engine) as db:
        leaving, project = _account(db, "leaving@example.com")
        staying, other_project = _account(db, "staying@example.com")
        db.add(Subscriber(email="install-wide@example.com"))  # attributed to no project
        db.commit()
        leaving_id, project_id = leaving.id, project.id

        accounts.erase(db, leaving)
        db.expire_all()

        assert db.get(User, leaving_id) is None
        assert _count(db, Project, user_id=leaving_id) == 0
        assert _count(db, Content, project_id=project_id) == 0
        assert _count(db, PlatformConnection, user_id=leaving_id) == 0
        assert _count(db, Webhook, user_id=leaving_id) == 0
        assert _count(db, ApiKey, user_id=leaving_id) == 0
        # Their audience's addresses go with them, not unattributed.
        assert _count(db, Subscriber, email="reader-of-leaving@example.com") == 0

        # The other account, and the install's own subscriber, are untouched.
        assert db.get(User, staying.id) is not None
        assert _count(db, Content, project_id=other_project.id) == 1
        assert _count(db, Subscriber, email="reader-of-staying@example.com") == 1
        assert _count(db, Subscriber, email="install-wide@example.com") == 1


def test_the_wrong_password_deletes_nothing(client, auth, user, db):
    resp = client.request("DELETE", ME, headers=auth, json={"password": "not-it"})
    assert resp.status_code == 403
    assert "nothing was deleted" in resp.json()["detail"]
    db.expire_all()
    assert db.get(User, user.id) is not None


def test_the_right_password_erases_the_account_and_its_sign_in(client, auth, user, db):
    resp = client.request("DELETE", ME, headers=auth, json={"password": "hunter2hunter2"})
    assert resp.status_code == 204
    db.expire_all()
    assert db.get(User, user.id) is None

    # The token it was holding no longer belongs to anyone,
    assert client.get(ME, headers=auth).status_code == 401
    # and the password no longer signs in.
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": "hunter2hunter2"}
    )
    assert login.status_code == 401


def test_feedback_signed_with_the_account_address_goes_with_it(client, auth, user, db):
    """Feedback has no account column; an address typed into it is the only
    link. One signed with this account's address — in any case — went on
    being kept for a year after the account asked to be forgotten."""
    from app.models.feedback import Feedback

    db.add_all(
        [
            Feedback(category="bug", message="Theirs, signed.", email="DEV@Example.com"),
            Feedback(category="bug", message="Somebody else's.", email="other@example.com"),
            Feedback(category="general", message="Anonymous.", email=None),
        ]
    )
    db.commit()

    resp = client.request("DELETE", ME, headers=auth, json={"password": "hunter2hunter2"})

    assert resp.status_code == 204
    db.expire_all()
    left = {f.message for f in db.scalars(select(Feedback))}
    assert left == {"Somebody else's.", "Anonymous."}


def test_it_needs_the_password_and_a_session(client, auth):
    assert client.request("DELETE", ME, headers=auth, json={}).status_code == 422
    assert client.request("DELETE", ME, json={"password": "hunter2hunter2"}).status_code == 401
