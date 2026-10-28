"""A feed reader polling for news gets a 304 when there is none (C104 M8).

Readers poll on a timer and nearly every poll finds the feed unchanged. It went
out ``no-store``, like account data, so each poll was the whole XML. Now it
carries an ETag and a short public lifetime, and a poll that sends the ETag
back gets a 304 with no body until the feed actually changes.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.routers.projects import FEED_MAX_AGE_SECONDS


@pytest.fixture
def feed(project, db) -> str:
    db.add(Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, title="Pulse 1.0",
        slug="pulse-1-0", status=ContentStatus.PUBLISHED, published_at=utcnow(),
    ))
    db.commit()
    return f"/api/v1/projects/{project.id}/feed.xml"


def test_the_feed_is_cacheable_and_tagged(client, feed):
    resp = client.get(feed)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == f"public, max-age={FEED_MAX_AGE_SECONDS}"
    assert resp.headers["etag"].startswith('"')


@pytest.mark.parametrize(
    "send",
    [lambda tag: tag, lambda tag: "W/" + tag, lambda tag: f'"other", {tag}', lambda tag: "*"],
    ids=["exact", "weak", "in-a-list", "wildcard"],
)
def test_an_unchanged_feed_is_a_304_with_no_body(client, feed, send):
    tag = client.get(feed).headers["etag"]
    resp = client.get(feed, headers={"If-None-Match": send(tag)})

    assert resp.status_code == 304
    assert resp.content == b""
    assert resp.headers["etag"] == tag


def test_a_new_item_changes_the_tag(client, feed, project, db):
    tag = client.get(feed).headers["etag"]
    db.add(Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, title="Pulse 1.1",
        slug="pulse-1-1", status=ContentStatus.PUBLISHED, published_at=utcnow(),
    ))
    db.commit()

    resp = client.get(feed, headers={"If-None-Match": tag})
    assert resp.status_code == 200
    assert "Pulse 1.1" in resp.text
    assert resp.headers["etag"] != tag


def test_a_stale_tag_gets_the_feed(client, feed):
    resp = client.get(feed, headers={"If-None-Match": '"not-this-one"'})
    assert resp.status_code == 200
    assert "Pulse 1.0" in resp.text


def test_a_missing_feed_is_still_an_uncacheable_404(client):
    resp = client.get("/api/v1/projects/999999/feed.xml")
    assert resp.status_code == 404
    assert resp.headers["cache-control"] == "no-store"
