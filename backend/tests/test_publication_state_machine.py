"""The publication status machine, from the worker's side (C104 M3).

``publish_one`` and ``cancel_publication`` are what a broker delivers, and a
broker delivers at least once — so each is run twice on a row in every status.
Only ``pending`` and a due ``scheduled`` row are claimed, and a claimed row is
sent exactly once; only those two can be cancelled; ``publishing`` (in flight
on another worker) and the three terminal states are left exactly as they are.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.services.publishers import base

P = PublicationStatus


@pytest.fixture
def sent(monkeypatch, task_session, connect) -> list[str]:
    import app.tasks.publish_tasks as publish_tasks

    connect("devto")
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(base, "_sleep", lambda _s: None)
    calls: list[str] = []

    def fake(method, url, **_kwargs):
        calls.append(method)
        return httpx.Response(
            201, json={"id": 7, "url": "https://dev.to/a/x"}, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(base, "_exchange", fake)
    return calls


def _row(db, project, status: PublicationStatus) -> Publication:
    piece = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED, title="T", slug=f"t-{status.value}",
        body_markdown="body " * 50,
    )
    db.add(piece)
    db.flush()
    row = Publication(
        content_id=piece.id, platform=Platform.DEVTO, status=status,
        scheduled_for=utcnow() - timedelta(minutes=1) if status == P.SCHEDULED else None,
        published_at=utcnow() if status == P.PUBLISHED else None,
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    ("start", "sends", "after"),
    [
        (P.PENDING, 1, P.PUBLISHED),
        (P.SCHEDULED, 1, P.PUBLISHED),
        (P.PUBLISHING, 0, P.PUBLISHING),
        (P.PUBLISHED, 0, P.PUBLISHED),
        (P.FAILED, 0, P.FAILED),
        (P.CANCELLED, 0, P.CANCELLED),
    ],
)
def test_delivering_publish_twice_sends_at_most_once(db, project, sent, start, sends, after):
    from app.tasks import publish_tasks

    row = _row(db, project, start)
    publish_tasks.publish_one(row.id)
    second = publish_tasks.publish_one(row.id)

    db.expire_all()
    row = db.get(Publication, row.id)
    assert len(sent) == sends
    assert row.status == after
    assert row.attempts == sends
    assert second["skipped"] is True


def test_a_scheduled_row_not_yet_due_is_not_claimed(db, project, sent):
    from app.tasks import publish_tasks

    row = _row(db, project, P.SCHEDULED)
    row.scheduled_for = utcnow() + timedelta(hours=1)
    db.commit()

    publish_tasks.publish_one(row.id)

    db.expire_all()
    assert sent == []
    assert db.get(Publication, row.id).status == P.SCHEDULED


@pytest.mark.parametrize(
    ("start", "cancelled"),
    [
        (P.PENDING, True),
        (P.SCHEDULED, True),
        (P.PUBLISHING, False),
        (P.PUBLISHED, False),
        (P.FAILED, False),
        (P.CANCELLED, False),
    ],
)
def test_cancel_takes_only_rows_that_have_not_started(db, project, sent, start, cancelled):
    from app.tasks import publish_tasks

    row = _row(db, project, start)
    first = publish_tasks.cancel_publication(row.id)
    second = publish_tasks.cancel_publication(row.id)

    db.expire_all()
    row = db.get(Publication, row.id)
    assert first["cancelled"] is cancelled
    assert second["cancelled"] is False
    assert row.status == (P.CANCELLED if cancelled else start)
    if cancelled:
        assert row.scheduled_for is None


def test_publishing_moves_the_piece_to_published(db, project, sent):
    from app.tasks import publish_tasks

    row = _row(db, project, P.PENDING)
    publish_tasks.publish_one(row.id)

    db.expire_all()
    piece = db.get(Content, row.content_id)
    assert piece.status == ContentStatus.PUBLISHED
    assert piece.published_at is not None
