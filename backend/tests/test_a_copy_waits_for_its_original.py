"""A syndicated copy does not go out ahead of its original (C104 M2).

``queue`` sets each copy a fixed delay behind the original — a guess made at
queue time. When the original then fails with something retryable and is parked
for later, the guess is wrong: the copies came due at their own time and went
out with no ``rel=canonical``, which cannot be fixed once they are live. The
sweep now holds a copy behind the original's own time, the rule a hand retry
already followed (``retry_hold``), and stops holding once the original has
finished — published, or given up on.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import as_aware, utcnow
from app.models.publication import Platform, PublicationStatus
from app.services import publishing_service
from app.services.publishers import base


@pytest.fixture
def piece(db, project, connect) -> Content:
    connect("devto", "mastodon")
    project.auto_canonical = True
    project.canonical_platform = Platform.DEVTO
    row = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=ContentStatus.APPROVED,
        title="Retries", slug="retries", body_markdown="word " * 100,
    )
    db.add(row)
    db.commit()
    return row


def _rows(db, piece):
    publishing_service.queue(db, piece, [Platform.DEVTO, Platform.MASTODON])
    db.commit()
    by = {p.platform: p for p in piece.publications}
    return by[Platform.DEVTO], by[Platform.MASTODON]


def test_a_copy_due_while_its_original_is_parked_waits_behind_it(db, piece):
    original, copy = _rows(db, piece)
    # The original failed with something retryable and is parked an hour out;
    # the copy's own queue-time slot has arrived.
    original.status = PublicationStatus.SCHEDULED
    original.attempts = 1
    original.scheduled_for = utcnow() + timedelta(hours=1)
    copy.status = PublicationStatus.PUBLISHING
    copy.scheduled_for = utcnow() - timedelta(minutes=1)
    db.commit()

    publishing_service.execute(db, copy)

    db.refresh(copy)
    assert copy.status == PublicationStatus.SCHEDULED
    assert copy.attempts == 0  # waiting is not an attempt
    assert copy.error is None
    delay = timedelta(seconds=settings.syndication_delay_seconds)
    expected = as_aware(original.scheduled_for) + delay
    assert abs((as_aware(copy.scheduled_for) - expected).total_seconds()) < 5


@pytest.mark.parametrize("finished", [PublicationStatus.FAILED, PublicationStatus.CANCELLED])
def test_a_copy_stops_waiting_once_the_original_has_given_up(db, piece, finished):
    original, copy = _rows(db, piece)
    original.status = finished
    original.scheduled_for = None
    copy.status = PublicationStatus.PUBLISHING
    db.commit()

    publishing_service.execute(db, copy)

    db.refresh(copy)
    # Attempted, not re-parked. (It fails here on the fixture's credentials,
    # which is beside the point: an original that is not going out is not
    # something to wait for.)
    assert copy.attempts == 1


def test_the_original_itself_is_never_held(db, piece, monkeypatch):
    original, _copy = _rows(db, piece)
    original.status = PublicationStatus.PUBLISHING
    db.commit()
    monkeypatch.setattr(
        base,
        "_exchange",
        lambda m, u, **_k: httpx.Response(
            201, json={"id": 5, "url": "https://dev.to/a/r"}, request=httpx.Request(m, u)
        ),
    )

    publishing_service.execute(db, original)

    db.refresh(original)
    assert original.status == PublicationStatus.PUBLISHED
