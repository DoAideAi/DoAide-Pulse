"""Feedback is not kept for ever.

A feedback row can hold a visitor's email address, what they wrote and their
user agent. ``purge_old_feedback`` drops rows older than
``feedback_retention_days``, once a day, like the activity and product events
beside it.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings, settings
from app.models.feedback import Feedback
from app.tasks import maintenance_tasks
from app.tasks.celery_app import celery_app


@pytest.fixture
def task_db(monkeypatch, db):
    monkeypatch.setattr(maintenance_tasks, "SessionLocal", lambda: db)
    # The task closes its session; the test still needs this one afterwards.
    monkeypatch.setattr(db, "close", lambda: None)
    return db


def test_feedback_past_the_window_is_purged_and_the_rest_kept(task_db, monkeypatch):
    monkeypatch.setattr(settings, "feedback_retention_days", 365)
    now = datetime.now(UTC)
    task_db.add_all(
        [
            Feedback(category="bug", message="old", created_at=now - timedelta(days=400)),
            Feedback(category="bug", message="edge", created_at=now - timedelta(days=364)),
            Feedback(category="bug", message="new", created_at=now),
        ]
    )
    task_db.commit()

    assert maintenance_tasks.purge_old_feedback() == {"purged": 1}
    left = sorted(row.message for row in task_db.query(Feedback).all())
    assert left == ["edge", "new"]


def test_it_runs_daily():
    entry = celery_app.conf.beat_schedule["purge-old-feedback"]
    assert entry["task"] == "app.tasks.maintenance_tasks.purge_old_feedback"
    assert entry["schedule"] == 86400.0


def test_a_zero_window_is_refused():
    # Zero is not "keep for ever": it is a cutoff of now, deleting each row
    # the moment it is written.
    with pytest.raises(ValueError):
        Settings(feedback_retention_days=0)
