"""M3: cancelling a piece's queue does not rewrite a post that just went live.

``unschedule`` and every archiving path (``cancel_armed``) chose the rows to
cancel by the status the request had loaded, then assigned ``cancelled``. A
worker that claimed and finished a row in between had already committed
``published`` — and the request's write landed on top of it. The live post
lost its status, the piece no longer read as published, and the next Publish
re-armed the row and posted it a second time.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service
from tests.conftest import TestSession

LIVE = "https://dev.to/x/1"


@pytest.fixture
def piece(db, project):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.APPROVED,
        title="A piece",
        slug="a-piece",
        body_markdown="Body.",
        scheduled_for=utcnow() + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    for platform in (Platform.DEVTO, Platform.MEDIUM):
        db.add(
            Publication(
                content_id=row.id,
                platform=platform,
                status=PublicationStatus.SCHEDULED,
                scheduled_for=utcnow() + timedelta(hours=1),
            )
        )
    db.commit()
    db.refresh(row)
    return row


def _worker_publishes(content_id: int, platform: Platform) -> None:
    """Another process claims the row and records the post as live."""
    other = TestSession()
    try:
        row = next(
            p for p in other.get(Content, content_id).publications if p.platform == platform
        )
        row.status = PublicationStatus.PUBLISHED
        row.external_url = LIVE
        row.published_at = utcnow()
        other.commit()
    finally:
        other.close()


def _status(db, piece, platform):
    db.expire_all()
    return next(
        p for p in db.get(Content, piece.id).publications if p.platform == platform
    )


def test_archiving_leaves_a_row_published_mid_request_published(db, piece):
    # The request has loaded the queue: both rows read SCHEDULED.
    assert {p.status for p in piece.publications} == {PublicationStatus.SCHEDULED}
    _worker_publishes(piece.id, Platform.DEVTO)

    cancelled = publishing_service.cancel_armed(db, piece)
    db.commit()

    assert [p.platform for p in cancelled] == [Platform.MEDIUM]
    devto = _status(db, piece, Platform.DEVTO)
    assert devto.status == PublicationStatus.PUBLISHED
    assert devto.external_url == LIVE
    assert _status(db, piece, Platform.MEDIUM).status == PublicationStatus.CANCELLED


def test_unscheduling_leaves_a_row_published_mid_request_published(
    client, auth, db, piece, monkeypatch
):
    real = publishing_service.cancel_if
    raced = []

    def racing(db_, publication, *args, **kwargs):
        # The worker finishes Dev.to after the request chose its targets.
        if not raced:
            raced.append(True)
            _worker_publishes(piece.id, Platform.DEVTO)
        return real(db_, publication, *args, **kwargs)

    monkeypatch.setattr(publishing_service, "cancel_if", racing)

    resp = client.delete(f"/api/v1/content/{piece.id}/schedule", headers=auth)
    assert resp.status_code == 200, resp.text

    assert {p["platform"] for p in resp.json()} == {Platform.MEDIUM.value}
    devto = _status(db, piece, Platform.DEVTO)
    assert devto.status == PublicationStatus.PUBLISHED
    assert devto.external_url == LIVE
    # The piece reads as live, which it is.
    assert db.get(Content, piece.id).status == ContentStatus.PUBLISHED


def test_cancel_if_cancels_a_row_still_waiting(db, piece):
    row = piece.publications[0]
    assert publishing_service.cancel_if(
        db, row, (PublicationStatus.SCHEDULED,), error="withdrawn"
    )
    db.commit()
    assert row.status == PublicationStatus.CANCELLED
    assert row.scheduled_for is None
    assert row.error == "withdrawn"


def test_the_cancel_task_leaves_a_row_published_mid_task_published(
    db, piece, monkeypatch, task_session
):
    from app.tasks import publish_tasks

    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    devto = next(p for p in piece.publications if p.platform == Platform.DEVTO)
    real = publishing_service.cancel_if

    def racing(db_, publication, *args, **kwargs):
        _worker_publishes(piece.id, Platform.DEVTO)
        return real(db_, publication, *args, **kwargs)

    monkeypatch.setattr(publishing_service, "cancel_if", racing)

    assert publish_tasks.cancel_publication(devto.id)["cancelled"] is False
    row = _status(db, piece, Platform.DEVTO)
    assert row.status == PublicationStatus.PUBLISHED
    assert row.external_url == LIVE
