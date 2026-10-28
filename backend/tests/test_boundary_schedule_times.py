"""Boundary values for publish times (C104 M1).

``POST /content/{id}/publish`` and the calendar's reschedule take a
``timezone`` for a naive time; ``POST /content/{id}/schedule`` refused the
field as unknown, so the same "09:00" meant 09:00 in the user's zone on one
endpoint and 09:00 UTC on the other, and a time inside a DST change got no
handling there at all. The rest pins the edges the probe found already right,
so they stay that way on both endpoints.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow

ENDPOINTS = ["publish", "schedule"]


@pytest.fixture(autouse=True)
def _ready(connect, monkeypatch):
    import app.routers.content as content_router

    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(content_router, "_dispatch", lambda ids: None)
    connect("devto")


@pytest.fixture
def piece(db, project) -> int:
    row = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=ContentStatus.APPROVED,
        title="T", slug="t", body_markdown="body " * 50,
    )
    db.add(row)
    db.commit()
    return row.id


def _send(client, auth, piece, endpoint, **payload):
    return client.post(
        f"/api/v1/content/{piece}/{endpoint}", headers=auth, json={"platforms": ["devto"], **payload}
    )


def _soon_naive(month_day: str) -> str:
    """A date within the scheduling horizon, as a naive local time."""
    year = utcnow().year + (1 if utcnow().strftime("%m-%d") >= month_day else 0)
    return f"{year}-{month_day}T09:00:00"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_naive_time_is_read_in_the_zone_given(client, auth, piece, endpoint):
    local = _soon_naive("07-01") if utcnow().month < 6 else _soon_naive("01-15")
    resp = _send(client, auth, piece, endpoint, scheduled_for=local, timezone="Asia/Kolkata")
    assert resp.status_code == 200, resp.text
    # 09:00 in Kolkata is 03:30 UTC, all year (no DST there).
    assert resp.json()[0]["scheduled_for"].endswith("T03:30:00")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_an_explicit_offset_beats_the_zone(client, auth, piece, endpoint):
    local = _soon_naive("07-01") if utcnow().month < 6 else _soon_naive("01-15")
    resp = _send(client, auth, piece, endpoint, scheduled_for=local + "Z", timezone="Asia/Kolkata")
    assert resp.json()[0]["scheduled_for"].endswith("T09:00:00")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_time_the_clocks_skip_is_refused_with_the_reason(client, auth, piece, endpoint, monkeypatch):
    # 02:30 on the second Sunday of March 2027 does not exist in New York. The
    # horizon is widened so the test does not depend on today's date.
    monkeypatch.setattr(settings, "schedule_max_horizon_days", 3650)
    resp = _send(
        client, auth, piece, endpoint,
        scheduled_for="2027-03-14T02:30:00", timezone="America/New_York",
    )
    assert resp.status_code == 422
    assert "does not exist in America/New_York" in resp.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_an_unknown_zone_is_refused_by_name(client, auth, piece, endpoint):
    resp = _send(client, auth, piece, endpoint, scheduled_for=_soon_naive("07-01"), timezone="Mars/Base")
    assert resp.status_code == 422
    assert "Mars/Base" in resp.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "when",
    ["2999-01-01T00:00:00Z", "9999-12-31T23:59:59Z", 4102444800],
    ids=["year-2999", "year-9999", "epoch-2100"],
)
def test_a_time_past_the_horizon_is_refused(client, auth, piece, endpoint, when):
    resp = _send(client, auth, piece, endpoint, scheduled_for=when)
    assert resp.status_code == 422
    assert "check the year" in resp.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "when",
    ["2027-02-29T09:00:00Z", "next tuesday", "", "2027-03-10T09:00:00+25:00"],
    ids=["feb-29-non-leap", "words", "empty", "offset-out-of-range"],
)
def test_a_time_that_is_not_one_is_refused(client, auth, piece, endpoint, when):
    assert _send(client, auth, piece, endpoint, scheduled_for=when).status_code == 422


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_time_an_hour_ago_is_refused_but_clock_skew_is_not(client, auth, db, project, endpoint):
    def fresh():
        row = Content(
            project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
            status=ContentStatus.APPROVED, title="S", slug=f"s-{utcnow().timestamp()}",
            body_markdown="body " * 50,
        )
        db.add(row)
        db.commit()
        return row.id

    hour_ago = (utcnow() - timedelta(hours=1)).isoformat()
    assert _send(client, auth, fresh(), endpoint, scheduled_for=hour_ago).status_code == 422

    skew = (utcnow() - timedelta(seconds=settings.schedule_past_grace_seconds // 2)).isoformat()
    assert _send(client, auth, fresh(), endpoint, scheduled_for=skew).status_code == 200


def test_schedule_asks_for_a_time_or_optimize_and_not_both(client, auth, piece):
    neither = _send(client, auth, piece, "schedule")
    assert neither.status_code == 400 and "optimize" in neither.text
    both = _send(client, auth, piece, "schedule", scheduled_for=_soon_naive("07-01") + "Z", optimize=True)
    assert both.status_code == 400 and "not both" in both.text



#: Instants at the edge of the calendar that their offset carries off it: the
#: first is before year 1 in UTC, the second after year 9999. Converting them
#: raised ``OverflowError`` and every scheduling route answered 500.
OFF_THE_CALENDAR = ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-12:00"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("when", OFF_THE_CALENDAR, ids=["before-year-1", "after-year-9999"])
def test_a_time_off_the_calendar_is_refused(client, auth, piece, endpoint, when):
    resp = _send(client, auth, piece, endpoint, scheduled_for=when)
    assert resp.status_code == 422, resp.text
    assert "check the year" in resp.text


@pytest.mark.parametrize("when", OFF_THE_CALENDAR, ids=["before-year-1", "after-year-9999"])
def test_a_batch_scheduled_off_the_calendar_fails_each_piece(client, auth, piece, when):
    resp = client.post(
        "/api/v1/content/bulk/publish",
        headers=auth,
        json={"content_ids": [piece], "platforms": ["devto"], "scheduled_for": when},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == []
    assert "check the year" in body["failed"][0]["reason"]


@pytest.mark.parametrize(
    "params",
    [{"start": "9999-12-31T00:00:00Z"}, {"end": "0001-01-01T00:00:00Z"}],
    ids=["start-at-the-last-day", "end-at-the-first-day"],
)
def test_a_calendar_window_at_the_edge_stops_there(client, auth, params):
    # A one-sided window runs 60 days from the bound given, which past either
    # end of the calendar used to raise ``OverflowError`` as a 500.
    resp = client.get("/api/v1/calendar", headers=auth, params=params)
    assert resp.status_code == 200, resp.text
    assert resp.json()["entries"] == []
