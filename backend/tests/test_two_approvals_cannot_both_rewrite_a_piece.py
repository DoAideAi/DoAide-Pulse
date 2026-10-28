"""Approving runs the SEO autofix, which rewrites the piece — so two writers
on one piece must not both win.

The approve path repairs title, meta description and body (``seo_autofix``)
before committing. A second writer that saved the piece in between — another
approval, an editor's autosave — would otherwise have its write replaced by an
autofix computed from the copy this request loaded. ``Content.version`` makes
the later commit a ``StaleDataError``, answered as a 409; this pins that the
approve door goes through it rather than around it.
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.content import Content, ContentStatus, ContentType


def test_an_approval_over_a_newer_write_is_a_409_and_keeps_the_newer_write(
    client, auth, db, project, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "content_quality_gate_enabled", True)
    piece = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.REVIEW,
        title="Short",
        slug="short",
        body_markdown="A body long enough to be worth approving. " * 40,
        meta_description="Too short.",
    )
    db.add(piece)
    db.commit()
    db.refresh(piece)
    loaded_version = piece.version

    # Somebody else saves the piece after this session loaded it.
    db.execute(
        text("UPDATE content SET title = :t, version = version + 1 WHERE id = :id"),
        {"t": "The other writer's title", "id": piece.id},
    )
    # Committed without expiring, so this session still holds the copy it
    # loaded — the position a concurrent request is in.
    db.expire_on_commit = False
    db.commit()
    db.expire_on_commit = True

    resp = client.post(f"/api/v1/content/{piece.id}/approve?force=true", headers=auth)

    assert resp.status_code == 409, resp.text
    db.rollback()
    db.expire_all()
    fresh = db.get(Content, piece.id)
    assert fresh.title == "The other writer's title"
    assert fresh.version == loaded_version + 1
    assert fresh.status == ContentStatus.REVIEW
