"""A calendar window is never one that ends before it starts.

``end`` before ``start`` was a 200 with no entries, which the page reads as
"nothing scheduled". And ``start`` alone more than a month out was the same
thing by accident: ``end`` defaulted to a month from *now*, before ``start``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus
from app.routers import calendar as calendar_router


def _iso(dt: datetime) -> str:
    # Naive: a '+' in a query string is decoded as a space.
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _scheduled(db, project, when: datetime) -> None:
    content = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        title="Later",
        slug="later",
        status=ContentStatus.APPROVED,
    )
    db.add(content)
    db.flush()
    db.add(
        Publication(
            content_id=content.id,
            platform=Platform.DEVTO,
            status=PublicationStatus.SCHEDULED,
            scheduled_for=when,
        )
    )
    db.commit()


def test_end_before_start_is_refused(client, auth):
    now = datetime.now(UTC)
    resp = client.get(
        f"/api/v1/calendar?start={_iso(now)}&end={_iso(now - timedelta(days=1))}",
        headers=auth,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == calendar_router.WINDOW_INVERTED
    assert "Swap them" in resp.json()["detail"]


def test_start_alone_far_ahead_shows_what_is_scheduled_there(client, auth, db, project):
    start = datetime.now(UTC) + timedelta(days=90)
    _scheduled(db, project, start + timedelta(days=10))
    resp = client.get(f"/api/v1/calendar?start={_iso(start)}", headers=auth)
    assert resp.status_code == 200
    assert [e["title"] for e in resp.json()["entries"]] == ["Later"]


def test_end_alone_far_back_shows_what_was_scheduled_there(client, auth, db, project):
    end = datetime.now(UTC) - timedelta(days=90)
    _scheduled(db, project, end - timedelta(days=10))
    resp = client.get(f"/api/v1/calendar?end={_iso(end)}", headers=auth)
    assert resp.status_code == 200
    assert [e["title"] for e in resp.json()["entries"]] == ["Later"]


def test_a_zero_width_window_is_allowed(client, auth):
    now = _iso(datetime.now(UTC))
    assert client.get(f"/api/v1/calendar?start={now}&end={now}", headers=auth).status_code == 200
