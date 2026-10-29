"""A trigger's ``every_hours`` has the same floor through the API as in the form.

The trigger builder offers half an hour as the shortest interval
(``frontend/src/lib/triggers.js``: ``min: "0.5"``). The API took any positive
number — ``0.01`` is thirty-six seconds — and the ten-minute sweep then found
the trigger due on every pass. For a schedule trigger with no pinned hour that
is a new piece every ten minutes until the daily cap stops it; for a GitHub
trigger it is six calls an hour against an allowance of sixty, per trigger.
"""
from __future__ import annotations

import pytest

from app.models.trigger import Trigger, TriggerKind
from app.schemas.trigger import MIN_INTERVAL_HOURS
from app.services import triggers

V1 = "/api/v1"


def _create(client, auth, project, every_hours):
    return client.post(
        f"{V1}/triggers",
        headers=auth,
        json={
            "project_id": project.id,
            "kind": "schedule",
            "name": "Often",
            "config": {"topic": "News", "every_hours": every_hours},
        },
    )


@pytest.mark.parametrize("hours", [0.01, 0.1, 0.25, 0.49])
def test_an_interval_below_the_floor_is_refused(client, auth, project, hours):
    resp = _create(client, auth, project, hours)
    assert resp.status_code == 422
    assert "every_hours" in resp.text


@pytest.mark.parametrize("hours", [0.5, 1, 24])
def test_the_floor_and_above_are_accepted(client, auth, project, hours):
    assert _create(client, auth, project, hours).status_code == 201


def test_the_floor_is_the_one_the_form_offers():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "lib" / "triggers.js"
    ).read_text()
    assert f'min: "{MIN_INTERVAL_HOURS:g}"' in source


def test_a_stored_interval_below_the_floor_is_read_as_the_floor(db, project):
    """Rows written before the check keep their value; the sweep must not act on it."""
    trigger = Trigger(
        project_id=project.id, kind=TriggerKind.SCHEDULE, name="Legacy",
        config={"topic": "News", "every_hours": 0.01}, state={},
    )
    db.add(trigger)
    db.commit()

    assert triggers.interval_hours(trigger) == MIN_INTERVAL_HOURS
