"""Page views and actions the browser reports, read back per account, purged by age."""
from __future__ import annotations

from datetime import timedelta

from app.config import settings
from app.models.activity import ActivityEvent
from app.models.mixins import utcnow
from app.models.user import User
from app.security import hash_password
from app.services import activity
from app.tasks import maintenance_tasks
from app.tasks.celery_app import celery_app

URL = "/api/v1/activity"


def _batch(*events):
    return {"events": list(events)}


def test_a_batch_is_recorded_for_the_caller(client, auth, db, user):
    resp = client.post(
        URL,
        json=_batch(
            {"kind": "page_view", "name": "/content", "path": "/content?status=review"},
            {"kind": "action", "name": "approve", "path": "/content/4"},
        ),
        headers=auth,
    )

    assert resp.status_code == 204, resp.text
    rows = db.query(ActivityEvent).order_by(ActivityEvent.id).all()
    assert [(r.user_id, r.kind, r.name) for r in rows] == [
        (user.id, "page_view", "/content"),
        (user.id, "action", "approve"),
    ]


def test_recording_needs_a_signed_in_user(client):
    resp = client.post(URL, json=_batch({"kind": "action", "name": "x"}))
    assert resp.status_code == 401


def test_an_unknown_kind_is_rejected(client, auth, db):
    resp = client.post(URL, json=_batch({"kind": "click", "name": "x"}), headers=auth)
    assert resp.status_code == 422
    assert db.query(ActivityEvent).count() == 0


def test_an_empty_or_oversized_batch_is_rejected(client, auth):
    assert client.post(URL, json=_batch(), headers=auth).status_code == 422
    too_many = [{"kind": "action", "name": "x"}] * 51
    assert client.post(URL, json=_batch(*too_many), headers=auth).status_code == 422


def test_the_summary_counts_only_the_caller_and_only_the_window(client, auth, db, user):
    other = User(email="other@example.com", hashed_password=hash_password("x" * 12))
    db.add(other)
    db.commit()
    activity.record(
        db,
        user.id,
        [
            {"kind": "page_view", "name": "/content"},
            {"kind": "page_view", "name": "/content"},
            {"kind": "page_view", "name": "/analytics"},
            {"kind": "action", "name": "publish"},
        ],
    )
    activity.record(db, other.id, [{"kind": "page_view", "name": "/content"}])
    old = ActivityEvent(user_id=user.id, kind="page_view", name="/settings")
    db.add(old)
    db.flush()
    old.created_at = utcnow() - timedelta(days=40)
    db.commit()

    resp = client.get(f"{URL}/summary?days=30", headers=auth)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_views"] == 3
    assert body["actions"] == 1
    assert body["top_pages"] == [
        {"name": "/content", "count": 2},
        {"name": "/analytics", "count": 1},
    ]
    assert body["top_actions"] == [{"name": "publish", "count": 1}]
    assert len(body["by_day"]) == 1


def test_old_rows_are_purged_and_recent_ones_kept(db, user, task_session, monkeypatch):
    monkeypatch.setattr(maintenance_tasks, "SessionLocal", task_session)
    keep = ActivityEvent(user_id=user.id, kind="action", name="keep")
    drop = ActivityEvent(user_id=user.id, kind="action", name="drop")
    db.add_all([keep, drop])
    db.flush()
    drop.created_at = utcnow() - timedelta(days=settings.activity_retention_days + 1)
    db.commit()

    assert maintenance_tasks.purge_old_activity() == {"purged": 1}
    assert [r.name for r in db.query(ActivityEvent).all()] == ["keep"]


def test_the_purge_rides_the_existing_beat_schedule():
    entry = celery_app.conf.beat_schedule["purge-old-activity"]
    assert entry["task"] == "app.tasks.maintenance_tasks.purge_old_activity"
    assert entry["schedule"] == 86400.0
