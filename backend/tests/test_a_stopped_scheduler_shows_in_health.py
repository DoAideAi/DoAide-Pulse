"""A scheduler that has stopped shows in the health check (C104 M11).

When ``pulse-beat`` died, every probe stayed green: the database, Redis and the
workers were up and idle, and nothing fired the sweep that publishes anything.
Scheduled posts simply stopped going out. ``/health/detail`` now reads the
queue itself — publications well past due and still waiting — and reports
``scheduler: behind`` with how many and how late, and logs it. A row parked for
a retry has a future time and does not count; neither does one just come due.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service

URL = "/api/v1/health/detail"


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED, title="T", slug="t", body_markdown="b",
    )
    db.add(row)
    db.commit()
    return row


def _row(db, piece, status, *, due_minutes_ago, platform=Platform.DEVTO):
    when = utcnow() - timedelta(minutes=due_minutes_ago)
    row = Publication(
        content_id=piece.id, platform=platform, status=status,
        scheduled_for=when if status == PublicationStatus.SCHEDULED else None,
    )
    db.add(row)
    db.flush()
    row.updated_at = when
    db.commit()
    return row


def _scheduler(client, auth):
    resp = client.get(URL, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_an_empty_queue_is_ok(client, auth):
    assert _scheduler(client, auth)["scheduler"]["status"] == "ok"


def test_rows_parked_in_the_future_or_just_due_are_ok(client, auth, db, piece):
    _row(db, piece, PublicationStatus.SCHEDULED, due_minutes_ago=-60)  # an hour away
    _row(db, piece, PublicationStatus.PENDING, due_minutes_ago=1, platform=Platform.MASTODON)
    assert _scheduler(client, auth)["scheduler"]["status"] == "ok"


def test_rows_long_past_due_are_behind_and_logged(client, auth, db, piece, caplog):
    late = settings.publish_scan_interval_seconds * publishing_service.BACKLOG_SWEEPS // 60 + 30
    _row(db, piece, PublicationStatus.SCHEDULED, due_minutes_ago=late)
    _row(
        db, piece, PublicationStatus.PENDING, due_minutes_ago=late + 10,
        platform=Platform.MASTODON,
    )
    caplog.set_level(logging.WARNING)

    body = _scheduler(client, auth)

    assert body["scheduler"]["status"] == "behind"
    assert body["scheduler"]["detail"].startswith("2 publications past due, the oldest by")
    assert "pulse-beat" in body["scheduler"]["detail"]
    # Reported, not folded into the overall status — like the worker probe.
    assert body["status"] == "ok"
    assert any("scheduled publishing is behind" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "status", [PublicationStatus.PUBLISHED, PublicationStatus.FAILED, PublicationStatus.CANCELLED]
)
def test_finished_rows_never_count(client, auth, db, piece, status):
    _row(db, piece, status, due_minutes_ago=600)
    assert _scheduler(client, auth)["scheduler"]["status"] == "ok"


def test_a_probe_that_fails_is_unknown_not_a_500(client, auth, monkeypatch):
    def boom(db, **kw):
        raise RuntimeError("database went away")

    monkeypatch.setattr(publishing_service, "backlog", boom)
    assert _scheduler(client, auth)["scheduler"]["status"] == "unknown"
