"""``{{date.*}}`` is the day where the writer is, not in Greenwich.

Pulse stores no timezone per account, so the built-ins were always computed in
UTC: a piece rendered at 01:30 in India — still the previous evening in UTC —
was dated yesterday. Render requests now take the same optional IANA
``timezone`` publish and schedule do, and the app sends the browser's.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.routers import templates as templates_router

API = "/api/v1/templates"
#: 20:00 UTC on the 28th is 01:30 on the 29th in Kolkata.
INSTANT = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return INSTANT.astimezone(tz) if tz else INSTANT.replace(tzinfo=None)


@pytest.fixture
def template_id(client, auth, project, monkeypatch):
    monkeypatch.setattr(templates_router, "datetime", _Frozen)
    resp = client.post(
        API,
        headers=auth,
        json={
            "name": "Dated",
            "title_template": "Update for {{date.long}}",
            "body_template": "Written {{date.today}}, {{date.month}} {{date.year}}.",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _render(client, auth, template_id, **extra):
    resp = client.post(f"{API}/{template_id}/preview", headers=auth, json={**extra})
    return resp


def test_the_date_is_the_writers_day(client, auth, template_id):
    resp = _render(client, auth, template_id, timezone="Asia/Kolkata")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Update for 29 October 2026"
    assert body["body"] == "Written 2026-10-29, October 2026."


def test_without_a_zone_it_is_utc_as_before(client, auth, template_id):
    body = _render(client, auth, template_id).json()
    assert body["title"] == "Update for 28 October 2026"


def test_an_unknown_zone_is_refused_in_words(client, auth, template_id):
    resp = _render(client, auth, template_id, timezone="Mars/Olympus")

    assert resp.status_code == 422
    assert "not a timezone I know" in resp.json()["detail"]
