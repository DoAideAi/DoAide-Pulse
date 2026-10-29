"""Triggers that are due are found however many that are not come first.

``due_triggers`` read the 200 active triggers checked longest ago and kept the
ones ``is_due`` passed. But "checked longest ago" is not "due": a weekly feed
checked six days ago sorts ahead of an hourly one checked two hours ago. An
account may hold a thousand triggers, and once two hundred of the slow ones
filled the page, a due trigger behind them was never checked at all — the same
page-then-filter starvation the retry sweep had.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.mixins import utcnow
from app.models.trigger import Trigger, TriggerKind
from app.services import triggers


def test_a_due_trigger_behind_a_page_of_slow_ones_is_found(db, project):
    now = utcnow()
    slow = [
        Trigger(
            project_id=project.id, kind=TriggerKind.RSS, name=f"weekly {i}",
            config={"feed_url": "https://example.com/feed.xml", "every_hours": 168},
            state={}, last_checked_at=now - timedelta(days=6),
        )
        for i in range(250)
    ]
    due = Trigger(
        project_id=project.id, kind=TriggerKind.RSS, name="hourly",
        config={"feed_url": "https://example.com/feed.xml", "every_hours": 1},
        state={}, last_checked_at=now - timedelta(hours=2),
    )
    db.add_all([*slow, due])
    db.commit()

    found = [t.id for t in triggers.due_triggers(db)]

    assert found == [due.id]


def test_the_cap_still_bounds_one_sweep(db, project):
    now = utcnow()
    db.add_all(
        Trigger(
            project_id=project.id, kind=TriggerKind.RSS, name=f"due {i}",
            config={"feed_url": "https://example.com/feed.xml", "every_hours": 1},
            state={}, last_checked_at=now - timedelta(hours=3),
        )
        for i in range(30)
    )
    db.commit()

    assert len(triggers.due_triggers(db, limit=10)) == 10
