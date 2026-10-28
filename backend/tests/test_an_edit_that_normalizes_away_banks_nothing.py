"""An edit that normalizes back to the stored value does not poison the history.

``PATCH /content/{id}`` asked "does this change the text?" of the raw request,
then normalized ``keywords``. ``["a"]`` normalizes to ``[]`` — so a revision
was banked under the current version, nothing in the row changed, the version
did not move, and the next genuine edit tried to bank the same
``(content_id, revision)`` again: ``uq_revision_per_content``, a 500, and a
piece nobody could edit until something else bumped its version.
"""
from __future__ import annotations

from app.models.content import Content
from app.models.revision import ContentRevision
from app.services import revisions


def _piece(client, auth, project) -> int:
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "content_type": "announcement",
            "title": "Launch",
            "body_markdown": "Body text " * 20,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_the_edit_after_a_normalized_away_one_still_saves(client, auth, project, db):
    content_id = _piece(client, auth, project)
    url = f"/api/v1/content/{content_id}"

    first = client.patch(url, headers=auth, json={"keywords": ["a"]})
    assert first.status_code == 200, first.text

    second = client.patch(url, headers=auth, json={"tags": ["release"]})
    assert second.status_code == 200, second.text
    assert second.json()["tags"] == ["release"]


def test_a_no_op_after_normalization_banks_no_revision(client, auth, project, db):
    content_id = _piece(client, auth, project)

    client.patch(f"/api/v1/content/{content_id}", headers=auth, json={"keywords": ["a"]})

    assert db.query(ContentRevision).filter_by(content_id=content_id).count() == 0


def test_snapshot_reuses_a_stored_revision_for_the_current_version(db, project):
    content = Content(
        project_id=project.id,
        content_type="announcement",
        title="T",
        slug="t",
        body_markdown="b",
    )
    db.add(content)
    db.commit()
    first = revisions.snapshot(db, content)
    db.commit()

    again = revisions.snapshot(db, content)
    db.commit()

    assert again.id == first.id
    assert db.query(ContentRevision).filter_by(content_id=content.id).count() == 1
