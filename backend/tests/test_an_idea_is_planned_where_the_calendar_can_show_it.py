"""An idea's planned day is one the calendar can still reach.

A planned idea leaves the backlog and is drawn only on its day, and the
calendar reads a year at most — so a mistyped year (2999 for 2026) filed the
idea where nobody would ever page to it. Held to the scheduling horizon either
side of today, as a scheduled publication's time already is.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.config import settings

HORIZON = settings.schedule_max_horizon_days


def _create(client, auth, project, planned):
    return client.post(
        "/api/v1/calendar/ideas",
        headers=auth,
        json={"project_id": project.id, "headline": "An idea", "planned_date": planned},
    )


@pytest.mark.parametrize("offset", [HORIZON + 1, -(HORIZON + 1), 365 * 900])
def test_a_day_past_the_horizon_is_refused(client, auth, project, offset):
    resp = _create(client, auth, project, (date.today() + timedelta(days=offset)).isoformat())
    assert resp.status_code == 422
    assert "check the year" in resp.text


@pytest.mark.parametrize("offset", [0, -1, HORIZON, -HORIZON])
def test_a_day_within_it_is_kept(client, auth, project, offset):
    planned = (date.today() + timedelta(days=offset)).isoformat()
    resp = _create(client, auth, project, planned)
    assert resp.status_code == 201
    assert resp.json()["planned_date"] == planned


def test_no_day_is_still_the_backlog(client, auth, project):
    resp = _create(client, auth, project, None)
    assert resp.status_code == 201
    assert resp.json()["planned_date"] is None


def test_replanning_is_held_to_the_same_horizon(client, auth, project):
    idea = _create(client, auth, project, None).json()
    far = (date.today() + timedelta(days=HORIZON + 1)).isoformat()
    resp = client.patch(
        f"/api/v1/calendar/ideas/{idea['id']}", headers=auth, json={"planned_date": far}
    )
    assert resp.status_code == 422
