"""A trigger check that waited in the queue behind its own twin does no work twice.

The beat sweep dispatches every due trigger each tick (ten minutes), and a
trigger stays due until its check *finishes*. With the worker behind — two
slots, one held by a long generation — each tick queued the same triggers
again, and every copy re-fetched the feed (or spent another of GitHub's sixty
unauthenticated calls an hour) when it reached the front. The duplicates were
deduplicated downstream, so nothing was posted twice; what they cost was the
queue's time, on a queue that was already behind.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.mixins import utcnow
from app.models.trigger import Trigger, TriggerKind
from app.services import feeds
from app.tasks import trigger_tasks


@pytest.fixture(autouse=True)
def _task_session(db, monkeypatch):
    class NoClose:
        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(trigger_tasks, "SessionLocal", NoClose)


@pytest.fixture
def rss_trigger(db, project) -> Trigger:
    trigger = Trigger(
        project_id=project.id,
        kind=TriggerKind.RSS,
        name="Changelog feed",
        config={"feed_url": "https://example.com/feed.xml", "every_hours": 6},
        state={},
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    return trigger


@pytest.fixture
def fetches(monkeypatch):
    calls = []

    def fetch(url, *args, **kwargs):
        calls.append(url)
        raise feeds.FeedError("the feed is down")

    monkeypatch.setattr(feeds, "fetch", fetch)
    return calls


def test_a_check_already_done_by_its_twin_does_not_fetch_again(db, rss_trigger, fetches):
    # The first copy ran a minute ago; this one sat in the queue behind it.
    rss_trigger.last_checked_at = utcnow() - timedelta(minutes=1)
    db.commit()

    result = trigger_tasks.check_trigger(rss_trigger.id)

    assert result == {"trigger_id": rss_trigger.id, "status": "not_due"}
    assert fetches == []
    db.refresh(rss_trigger)
    assert rss_trigger.consecutive_failures == 0


def test_a_due_trigger_is_still_checked(db, rss_trigger, fetches):
    rss_trigger.last_checked_at = utcnow() - timedelta(hours=7)
    db.commit()

    trigger_tasks.check_trigger(rss_trigger.id)

    assert fetches == ["https://example.com/feed.xml"]


def test_a_never_checked_trigger_is_checked(db, rss_trigger, fetches):
    trigger_tasks.check_trigger(rss_trigger.id)

    assert len(fetches) == 1
