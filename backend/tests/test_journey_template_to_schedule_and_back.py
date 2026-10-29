"""Journey: a release-notes template becomes a draft, goes on the schedule, is
moved, taken off again, shelved, and brought back.

Each step uses what the one before returned, and the mistakes a person really
makes along the way are made on purpose — a template filled without its
placeholder, a time already behind us, scheduling a piece that was archived —
to check that each is refused with something to act on and that the piece is
still usable afterwards. Nothing here publishes: the platform is only asked to
check the key, so the journey is entirely about what is armed and when.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.models.mixins import utcnow
from app.services.publishers import base

API = "/api/v1"


@pytest.fixture(autouse=True)
def buttondown(monkeypatch):
    """Buttondown accepts the key; nothing in this journey is due, so nothing sends."""

    def fake(method, url, **_kwargs):
        return httpx.Response(
            200, json={"username": "notes"}, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(base, "_exchange", fake)


def _rows(client, auth, piece_id):
    detail = client.get(f"{API}/content/{piece_id}", headers=auth).json()
    return detail, sorted((p["platform"], p["status"]) for p in detail["publications"])


def test_a_template_draft_through_the_schedule_and_back(client, auth, project):
    assert client.put(
        f"{API}/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd-key"}},
    ).status_code == 200

    # 1. A template, used once without its placeholder (refused) and once with.
    template = client.post(
        f"{API}/templates",
        headers=auth,
        json={
            "name": "Release notes",
            "mode": "literal",
            "content_type": "announcement",
            "title_template": "Release {{version}}",
            "body_template": "What changed in {{version}}. " + "Every change, explained. " * 30,
            "variables": [{"name": "version", "required": True}],
        },
    )
    assert template.status_code == 201, template.text
    template_id = template.json()["id"]
    unfilled = client.post(
        f"{API}/templates/{template_id}/use",
        headers=auth,
        json={"project_id": project.id, "values": {}},
    )
    assert unfilled.status_code == 422, unfilled.text
    assert "version" in unfilled.text
    used = client.post(
        f"{API}/templates/{template_id}/use",
        headers=auth,
        json={"project_id": project.id, "values": {"version": "2.4"}},
    )
    assert used.status_code == 201, used.text
    piece_id = used.json()["id"]
    assert used.json()["title"] == "Release 2.4"
    assert used.json()["status"] == "draft"

    # 2. Scheduled — first for a time already gone (refused), then for Friday.
    past = client.post(
        f"{API}/content/{piece_id}/schedule",
        headers=auth,
        json={
            "platforms": ["buttondown"],
            "scheduled_for": (utcnow() - timedelta(hours=2)).isoformat(),
        },
    )
    assert past.status_code == 422, past.text
    # Refused for being in the past, not for being unreadable.
    assert isinstance(past.json()["detail"], str), past.text
    friday = (utcnow() + timedelta(days=3)).replace(microsecond=0)
    scheduled = client.post(
        f"{API}/content/{piece_id}/schedule",
        headers=auth,
        json={"platforms": ["buttondown"], "scheduled_for": friday.isoformat()},
    )
    assert scheduled.status_code == 200, scheduled.text
    _, rows = _rows(client, auth, piece_id)
    assert rows == [("buttondown", "scheduled")]

    # 3. Dragged to Monday on the calendar.
    monday = friday + timedelta(days=3)
    moved = client.patch(
        f"{API}/calendar/content/{piece_id}",
        headers=auth,
        json={"scheduled_for": monday.isoformat()},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()[0]["scheduled_for"].startswith(monday.date().isoformat())

    # 4. Taken off the schedule: nothing armed, nothing on the calendar.
    assert client.delete(f"{API}/content/{piece_id}/schedule", headers=auth).status_code in (
        200,
        204,
    )
    detail, rows = _rows(client, auth, piece_id)
    assert rows == [("buttondown", "cancelled")]
    assert detail["scheduled_for"] is None
    window = {
        "start": utcnow().isoformat(),
        "end": (utcnow() + timedelta(days=30)).isoformat(),
    }
    calendar = client.get(f"{API}/calendar", headers=auth, params=window).json()["entries"]
    assert piece_id not in [e["content_id"] for e in calendar]

    # 5. Shelved: an archived piece cannot be scheduled, and says how to fix it.
    assert client.patch(
        f"{API}/content/{piece_id}", headers=auth, json={"status": "archived"}
    ).status_code == 200
    shelved = client.post(
        f"{API}/content/{piece_id}/schedule",
        headers=auth,
        json={"platforms": ["buttondown"], "scheduled_for": friday.isoformat()},
    )
    assert shelved.status_code == 409, shelved.text
    assert "archive" in shelved.json()["detail"].lower()

    # 6. Brought back, and the schedule takes again.
    assert client.patch(
        f"{API}/content/{piece_id}", headers=auth, json={"status": "draft"}
    ).status_code == 200
    again = client.post(
        f"{API}/content/{piece_id}/schedule",
        headers=auth,
        json={"platforms": ["buttondown"], "scheduled_for": friday.isoformat()},
    )
    assert again.status_code == 200, again.text
    _, rows = _rows(client, auth, piece_id)
    assert rows == [("buttondown", "scheduled")]
