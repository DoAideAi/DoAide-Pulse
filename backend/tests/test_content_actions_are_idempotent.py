"""Firing a content action twice is the same as firing it once (C104 M3).

A double click, a retried request after a dropped response, two tabs: each of
these sends the same transition again. None may add a second publication row,
spend an attempt, or move the piece somewhere the first call did not.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, connect):
    import app.routers.content as content_router

    monkeypatch.setattr(content_router, "_dispatch", lambda ids: None)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    connect("devto")


@pytest.fixture
def piece(db, project) -> int:
    row = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED, title="Pulse ships", slug="pulse-ships",
        body_markdown="Pulse ships. " * 80, meta_description="Pulse " + "m" * 80,
        keywords=["pulse"], focus_keyword="pulse",
    )
    db.add(row)
    db.commit()
    return row.id


def _later(days=2) -> str:
    return (utcnow() + timedelta(days=days)).isoformat()


def _state(db, piece_id):
    db.expire_all()
    content = db.get(Content, piece_id)
    return (
        content.status,
        content.scheduled_for,
        sorted((p.platform, p.status, p.attempts, p.scheduled_for) for p in content.publications),
    )


ACTIONS = {
    "approve": lambda c, a, i: c.post(f"/api/v1/content/{i}/approve", headers=a),
    "publish now": lambda c, a, i: c.post(
        f"/api/v1/content/{i}/publish", headers=a, json={"platforms": ["devto"]}
    ),
    "publish later": lambda c, a, i: c.post(
        f"/api/v1/content/{i}/publish", headers=a,
        json={"platforms": ["devto"], "scheduled_for": _later()},
    ),
    "schedule": lambda c, a, i: c.post(
        f"/api/v1/content/{i}/schedule", headers=a,
        json={"platforms": ["devto"], "scheduled_for": _later()},
    ),
    "archive": lambda c, a, i: c.post(
        f"/api/v1/content/{i}/status", headers=a, json={"status": "archived"}
    ),
}


@pytest.mark.parametrize("action", list(ACTIONS))
def test_twice_is_once(client, auth, db, piece, action):
    fire = ACTIONS[action]
    first = fire(client, auth, piece)
    assert first.status_code == 200, first.text
    after_one = _state(db, piece)

    second = fire(client, auth, piece)

    assert second.status_code == 200, second.text
    status, when, rows = _state(db, piece)
    assert (status, len(rows)) == (after_one[0], len(after_one[2]))
    assert [r[:3] for r in rows] == [r[:3] for r in after_one[2]]


def test_unscheduling_twice_cancels_once(client, auth, db, piece):
    ACTIONS["publish later"](client, auth, piece)
    first = client.delete(f"/api/v1/content/{piece}/schedule", headers=auth)
    second = client.delete(f"/api/v1/content/{piece}/schedule", headers=auth)

    assert first.status_code == second.status_code == 200
    assert len(first.json()) == 1 and second.json() == []


def test_retrying_twice_rearms_once(client, auth, db, piece):
    from app.models.publication import Platform, Publication, PublicationStatus

    db.add(Publication(
        content_id=piece, platform=Platform.DEVTO, status=PublicationStatus.FAILED,
        attempts=3, error="503",
    ))
    db.commit()
    first = client.post(f"/api/v1/content/{piece}/retry", headers=auth).json()
    second = client.post(f"/api/v1/content/{piece}/retry", headers=auth).json()

    assert len(first["retried"]) == 1
    # The row is pending now, so there is nothing left to retry.
    assert second["retried"] == []
    assert [s["reason"] for s in second["skipped"]] == ["Still pending"]


def test_a_reschedule_moves_the_one_row_rather_than_adding_one(client, auth, db, piece):
    ACTIONS["publish later"](client, auth, piece)
    resp = client.post(
        f"/api/v1/content/{piece}/publish", headers=auth,
        json={"platforms": ["devto"], "scheduled_for": _later(5)},
    )
    assert resp.status_code == 200
    _, _, rows = _state(db, piece)
    assert len(rows) == 1
    assert rows[0][3] > utcnow().replace(tzinfo=None) + timedelta(days=4)


def test_deleting_twice_answers_not_found_the_second_time(client, auth, piece):
    assert client.delete(f"/api/v1/content/{piece}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/content/{piece}", headers=auth).status_code == 404
