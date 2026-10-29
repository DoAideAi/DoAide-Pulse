"""A trigger pointed at a new feed or repo baselines it, whatever was polling.

Two halves of one problem.

**The edit.** ``PATCH /triggers/{id}`` replaced ``config`` and left ``state`` —
the *old* source's watermark — where it was. A feed trigger moved to another
feed found every one of its entries unseen and wrote a post about the newest,
however old; a GitHub trigger moved to another repo asked it for commits since
a sha it had never had, got a full page back and wrote "a lot has changed"
about the last hundred commits of somebody's history. A new source is supposed
to be baselined on its first poll, silently, like a new trigger.

**The poll already under way.** A check fetches first and writes its watermark
after — seconds, for a slow feed. An edit landing in between reset the state,
and the poll then committed the old source's ids over it (and fired about the
old source) under a config that no longer named it. The poll now re-reads the
source under a row lock before it writes anything, and stands down if it moved.
"""
from __future__ import annotations

import pytest
from sqlalchemy import update

from app.models.content import Content
from app.models.project import AutopilotMode
from app.models.trigger import Trigger, TriggerEvent, TriggerKind
from app.services import feeds, triggers

OLD = "https://old.example.com/feed.xml"
NEW = "https://new.example.com/feed.xml"

FEED_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>{title}</title>
  <item><title>{title} two</title><guid>{prefix}2</guid><link>https://x/2</link></item>
  <item><title>{title} one</title><guid>{prefix}1</guid><link>https://x/1</link></item>
</channel></rss>
"""


def _feed(prefix: str):
    return feeds.parse(FEED_XML.format(title=prefix.upper(), prefix=prefix))


@pytest.fixture
def writing_project(db, project):
    project.autopilot_mode = AutopilotMode.DRAFT
    db.commit()
    return project


@pytest.fixture
def rss_trigger(db, writing_project) -> Trigger:
    row = Trigger(
        project_id=writing_project.id,
        kind=TriggerKind.RSS,
        name="Changelog",
        config={"feed_url": OLD},
        state={"seen_ids": ["old1", "old2"], "feed_title": "OLD"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_a_new_feed_url_resets_what_the_trigger_has_seen(client, auth, db, rss_trigger):
    resp = client.patch(
        f"/api/v1/triggers/{rss_trigger.id}", headers=auth, json={"config": {"feed_url": NEW}}
    )

    assert resp.status_code == 200, resp.text
    db.refresh(rss_trigger)
    assert rss_trigger.state == {}


def test_the_first_poll_of_the_new_feed_baselines_and_writes_nothing(
    client, auth, db, rss_trigger, monkeypatch
):
    client.patch(
        f"/api/v1/triggers/{rss_trigger.id}", headers=auth, json={"config": {"feed_url": NEW}}
    )
    monkeypatch.setattr(feeds, "fetch", lambda url: _feed("new"))
    db.refresh(rss_trigger)

    result = triggers.check(db, rss_trigger)

    assert result["status"] == "baselined"
    assert db.query(Content).count() == 0


def test_an_edit_that_keeps_the_source_keeps_the_watermark(client, auth, db, rss_trigger):
    resp = client.patch(
        f"/api/v1/triggers/{rss_trigger.id}",
        headers=auth,
        json={"config": {"feed_url": OLD}, "name": "Renamed"},
    )

    assert resp.status_code == 200, resp.text
    db.refresh(rss_trigger)
    assert rss_trigger.state["seen_ids"] == ["old1", "old2"]


def test_a_poll_of_the_old_feed_cannot_write_over_the_edit(db, rss_trigger, monkeypatch):
    """The edit lands while the poll is fetching; the poll stands down."""

    def fetch_while_edited(url):
        assert url == OLD
        db.execute(
            update(Trigger)
            .where(Trigger.id == rss_trigger.id)
            .values(config={"feed_url": NEW}, state={})
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return _feed("old3")

    monkeypatch.setattr(feeds, "fetch", fetch_while_edited)

    result = triggers.check(db, rss_trigger)

    assert result["status"] == "source_changed"
    assert db.query(TriggerEvent).count() == 0
    db.expire_all()
    stored = db.get(Trigger, rss_trigger.id)
    assert stored.state == {}
    assert stored.config == {"feed_url": NEW}


def test_a_new_repo_resets_a_github_trigger(client, auth, db, writing_project):
    row = Trigger(
        project_id=writing_project.id,
        kind=TriggerKind.GITHUB,
        name="Repo",
        config={"repo": "acme/old"},
        state={"last_sha": "abc123", "last_tag": "v1.0.0"},
    )
    db.add(row)
    db.commit()

    resp = client.patch(
        f"/api/v1/triggers/{row.id}", headers=auth, json={"config": {"repo": "acme/new"}}
    )

    assert resp.status_code == 200, resp.text
    db.refresh(row)
    assert row.state == {}
