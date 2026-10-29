"""A tag rename writes each piece from what it holds when written, not when scanned.

``POST /tags/rename`` reads the account's tag lists in one statement, works out
the new lists, then loads the rows to change in a second one and writes. It
used to write the lists from the *first* read. An editor save that landed in
between — another tab, the autopilot tagging a fresh draft — was overwritten
with the list from before it, and nothing noticed: the second load picked up
the saved ``version``, so the optimistic lock that exists for exactly this
case passed.

The interleaving is staged by committing the "other" save from inside the
scan, the same way the request would see it from another connection.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.dialects import postgresql

from app.models.content import Content, ContentStatus, ContentType
from app.services import tags as tag_service


def _piece(db, project, tags: list[str]) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        title="Deploying Pulse",
        slug="deploying-pulse",
        body_markdown="Deploying Pulse with Docker.",
        excerpt="Deploying Pulse.",
        status=ContentStatus.DRAFT,
        tags=tags,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _edit_during_scan(monkeypatch, db, piece_id: int, tags: list[str]) -> None:
    """Commit someone else's save of ``tags`` the first time the scan matches."""
    real = tag_service.rename_in
    fired = []

    def rename_in(*args, **kwargs):
        if not fired:
            fired.append(True)
            db.execute(
                update(Content)
                .where(Content.id == piece_id)
                .values(tags=tags, version=Content.version + 1)
                .execution_options(synchronize_session=False)
            )
            db.commit()
        return real(*args, **kwargs)

    monkeypatch.setattr(tag_service, "rename_in", rename_in)


def test_a_tag_added_meanwhile_survives_the_rename(client, auth, db, project, monkeypatch):
    piece = _piece(db, project, ["guides", "news"])
    _edit_during_scan(monkeypatch, db, piece.id, ["guides", "news", "launch"])

    resp = client.post(
        "/api/v1/tags/rename", json={"old": "guides", "new": "howto"}, headers=auth
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["content_ids"] == [piece.id]
    db.expire_all()
    stored = db.get(Content, piece.id).tags
    assert "launch" in stored
    assert sorted(stored) == ["howto", "launch", "news"]


def test_a_piece_untagged_meanwhile_is_left_alone_and_not_counted(
    client, auth, db, project, monkeypatch
):
    """The other save removed the tag being renamed. The scan still counts
    the piece; the write must not put the renamed tag back on it."""
    piece = _piece(db, project, ["guides"])
    _edit_during_scan(monkeypatch, db, piece.id, ["news"])

    resp = client.post(
        "/api/v1/tags/rename", json={"old": "guides", "new": "howto"}, headers=auth
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 0
    assert resp.json()["content_ids"] == []
    db.expire_all()
    assert db.get(Content, piece.id).tags == ["news"]


def test_the_rows_being_rewritten_are_locked(client, auth, db, project, monkeypatch):
    """SQLite has no FOR UPDATE, so ask what Postgres would be sent."""
    piece = _piece(db, project, ["guides"])
    sent = []
    real_scalars = db.scalars

    def scalars(statement, *args, **kwargs):
        sent.append(str(statement.compile(dialect=postgresql.dialect())))
        return real_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalars", scalars)
    resp = client.post(
        "/api/v1/tags/rename", json={"old": "guides", "new": "howto"}, headers=auth
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["content_ids"] == [piece.id]
    assert any("FOR UPDATE" in sql for sql in sent)
