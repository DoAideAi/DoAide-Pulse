"""The content status machine, cell by cell (C104 M3).

Six states; four a caller may set (draft, review, approved, archived) and two
that follow from the publications (published, failed). Two doors reach the
column — ``POST /content/{id}/status`` and ``PATCH /content/{id}`` — and every
cell below is asserted through both, because a transition one allows and the
other refuses is a way round the refusal.

Each piece starts with the publication its status implies (a scheduled row for
``approved``, a published one for ``published``, a failed one for ``failed``),
so the side effects on that row are part of what is checked.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus

S = ContentStatus
P = PublicationStatus

#: The publication each starting status implies, if any.
_ROW_FOR = {S.APPROVED: P.SCHEDULED, S.PUBLISHED: P.PUBLISHED, S.FAILED: P.FAILED}

#: (from, to) -> (HTTP status, resulting content status, resulting row status)
MATRIX = {
    (S.DRAFT, S.DRAFT): (200, S.DRAFT, None),
    (S.DRAFT, S.REVIEW): (200, S.REVIEW, None),
    (S.DRAFT, S.APPROVED): (200, S.APPROVED, None),
    (S.DRAFT, S.ARCHIVED): (200, S.ARCHIVED, None),
    (S.REVIEW, S.DRAFT): (200, S.DRAFT, None),
    (S.REVIEW, S.REVIEW): (200, S.REVIEW, None),
    (S.REVIEW, S.APPROVED): (200, S.APPROVED, None),
    (S.REVIEW, S.ARCHIVED): (200, S.ARCHIVED, None),
    # Leaving approved calls off what it had armed; staying keeps it.
    (S.APPROVED, S.DRAFT): (200, S.DRAFT, P.CANCELLED),
    (S.APPROVED, S.REVIEW): (200, S.REVIEW, P.CANCELLED),
    (S.APPROVED, S.APPROVED): (200, S.APPROVED, P.SCHEDULED),
    (S.APPROVED, S.ARCHIVED): (200, S.ARCHIVED, P.CANCELLED),
    # Live on the platforms: only hiding it here is possible, and the live
    # post is not touched.
    (S.PUBLISHED, S.DRAFT): (409, S.PUBLISHED, P.PUBLISHED),
    (S.PUBLISHED, S.REVIEW): (409, S.PUBLISHED, P.PUBLISHED),
    (S.PUBLISHED, S.APPROVED): (409, S.PUBLISHED, P.PUBLISHED),
    (S.PUBLISHED, S.ARCHIVED): (200, S.ARCHIVED, P.PUBLISHED),
    # Out of the archive goes through draft or review, never straight to
    # approved — approving arms publications.
    (S.ARCHIVED, S.DRAFT): (200, S.DRAFT, None),
    (S.ARCHIVED, S.REVIEW): (200, S.REVIEW, None),
    (S.ARCHIVED, S.APPROVED): (409, S.ARCHIVED, None),
    (S.ARCHIVED, S.ARCHIVED): (200, S.ARCHIVED, None),
    # Failed rows are retried, not approved over.
    (S.FAILED, S.DRAFT): (200, S.DRAFT, P.FAILED),
    (S.FAILED, S.REVIEW): (200, S.REVIEW, P.FAILED),
    (S.FAILED, S.APPROVED): (409, S.FAILED, P.FAILED),
    (S.FAILED, S.ARCHIVED): (200, S.ARCHIVED, P.FAILED),
}


def test_the_matrix_covers_every_cell():
    settable = [S.DRAFT, S.REVIEW, S.APPROVED, S.ARCHIVED]
    assert set(MATRIX) == {(f, t) for f in ContentStatus for t in settable}


def _piece(db, project, status: ContentStatus) -> Content:
    row = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=status,
        title="Pulse ships", slug=f"p-{status.value}-{utcnow().timestamp()}",
        body_markdown="Pulse ships. " * 80, meta_description="Pulse " + "m" * 80,
        keywords=["pulse"], focus_keyword="pulse",
        published_at=utcnow() if status == S.PUBLISHED else None,
    )
    db.add(row)
    db.flush()
    if status in _ROW_FOR:
        row_status = _ROW_FOR[status]
        db.add(Publication(
            content_id=row.id, platform=Platform.DEVTO, status=row_status,
            scheduled_for=utcnow() + timedelta(days=1) if row_status == P.SCHEDULED else None,
            published_at=utcnow() if row_status == P.PUBLISHED else None,
        ))
    db.commit()
    return row


@pytest.mark.parametrize("door", ["status", "patch"])
@pytest.mark.parametrize(("start", "target"), list(MATRIX))
def test_each_transition(client, auth, db, project, connect, door, start, target):
    connect("devto")
    piece = _piece(db, project, start)
    if door == "status":
        resp = client.post(
            f"/api/v1/content/{piece.id}/status", headers=auth, json={"status": target.value}
        )
    else:
        resp = client.patch(
            f"/api/v1/content/{piece.id}", headers=auth, json={"status": target.value}
        )

    code, after, row_after = MATRIX[(start, target)]
    assert resp.status_code == code, resp.text
    db.expire_all()
    piece = db.get(Content, piece.id)
    assert piece.status == after
    if row_after is None:
        assert piece.publications == []
    else:
        assert [p.status for p in piece.publications] == [row_after]


@pytest.mark.parametrize("derived", [S.PUBLISHED, S.FAILED])
@pytest.mark.parametrize("door", ["status", "patch"])
def test_a_derived_status_cannot_be_set(client, auth, db, project, door, derived):
    piece = _piece(db, project, S.APPROVED)
    url = f"/api/v1/content/{piece.id}"
    body = {"status": derived.value}
    resp = (
        client.post(f"{url}/status", headers=auth, json=body)
        if door == "status"
        else client.patch(url, headers=auth, json=body)
    )
    assert resp.status_code == 422
    assert "cannot be set directly" in resp.text
    db.expire_all()
    assert db.get(Content, piece.id).status == S.APPROVED


def test_archive_and_back_is_a_round_trip_to_draft(client, auth, db, project, connect):
    """Reversibility: archiving an approved piece cancels its schedule;
    unarchiving brings it back as a draft, with nothing re-armed behind the
    user's back — publishing it again is a choice."""
    connect("devto")
    piece = _piece(db, project, S.APPROVED)
    url = f"/api/v1/content/{piece.id}/status"
    assert client.post(url, headers=auth, json={"status": "archived"}).status_code == 200
    assert client.post(url, headers=auth, json={"status": "draft"}).status_code == 200

    db.expire_all()
    piece = db.get(Content, piece.id)
    assert piece.status == S.DRAFT
    assert [p.status for p in piece.publications] == [P.CANCELLED]
