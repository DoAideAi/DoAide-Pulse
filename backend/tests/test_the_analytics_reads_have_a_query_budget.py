"""The read endpoints the earlier budgets did not cover stay flat (C104 M8).

``test_n_plus_one`` and its siblings pin the listings. The analytics reads, the
SEO post list, API keys and tags had no budget, so an N+1 introduced in any of
them would show up only as a slow dashboard. Each is measured at two sizes —
three published pieces, then nine, each on two platforms with three metric
snapshots — and must issue the same number of SELECTs at both.

The funnel and autopilot reports are pinned further: they read a status, dates
and ``source``, and loaded every piece's body and every publication row to do
it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.activity import ActivityEvent
from app.models.content import Content, ContentStatus, ContentType
from app.models.metrics import ContentMetric
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus

READS = [
    "/api/v1/analytics/overview",
    "/api/v1/analytics/features",
    "/api/v1/analytics/funnel",
    "/api/v1/analytics/autopilot",
    "/api/v1/analytics/top-content",
    "/api/v1/analytics/velocity",
    "/api/v1/analytics/alerts",
    "/api/v1/analytics/pipeline",
    "/api/v1/analytics/engagement-trend",
    "/api/v1/analytics/read-time",
    "/api/v1/analytics/subscribers",
    "/api/v1/analytics/published",
    "/api/v1/seo/posts",
    "/api/v1/api-keys",
    "/api/v1/tags",
    "/api/v1/metrics",
    "/api/v1/activity/summary",
]


def _seed(db, project, user, start, count):
    for i in range(start, start + count):
        piece = Content(
            project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
            status=ContentStatus.PUBLISHED, title=f"T{i}", slug=f"t{i}",
            body_markdown="word " * 300, published_at=utcnow() - timedelta(days=2),
            tags=[f"tag{i}"],
            source={"kind": "autopilot", "routing": {"auto": True, "candidate": True},
                    "seo_score": 80, "quality_score": 70},
        )
        db.add(piece)
        db.flush()
        for platform in (Platform.DEVTO, Platform.MASTODON):
            row = Publication(
                content_id=piece.id, platform=platform, status=PublicationStatus.PUBLISHED,
                published_at=utcnow() - timedelta(days=2),
                external_url=f"https://example.com/{i}/{platform.value}",
            )
            db.add(row)
            db.flush()
            for hours in (40, 20, 2):
                db.add(ContentMetric(
                    publication_id=row.id, captured_at=utcnow() - timedelta(hours=hours),
                    views=100 * (50 - hours), reactions=hours,
                ))
        db.add(ActivityEvent(
            user_id=user.id, kind="action", name="POST /content/:id/approve", path="/x"
        ))
    db.commit()


def _selects(client, auth, db, sql_log, url) -> list[str]:
    db.expire_all()
    sql_log.clear()
    assert client.get(url, headers=auth).status_code == 200, url
    return [s for s in sql_log if s.lstrip().upper().startswith("SELECT")]


@pytest.fixture
def two_sizes(client, auth, db, project, user, sql_log):
    def measure(url):
        _seed(db, project, user, 0, 3)
        small = len(_selects(client, auth, db, sql_log, url))
        _seed(db, project, user, 3, 6)
        large = len(_selects(client, auth, db, sql_log, url))
        return small, large

    return measure


@pytest.mark.parametrize("url", READS)
def test_the_query_count_does_not_grow_with_the_data(two_sizes, url):
    small, large = two_sizes(url)
    assert small == large, f"{url}: {small} SELECTs for 3 pieces, {large} for 9"


@pytest.mark.parametrize("url", ["/api/v1/analytics/funnel", "/api/v1/analytics/autopilot"])
def test_the_reports_read_no_bodies_and_no_publications(
    client, auth, db, project, user, sql_log, url
):
    _seed(db, project, user, 0, 3)
    statements = _selects(client, auth, db, sql_log, url)

    assert not any("body_markdown" in s for s in statements), url
    assert not any("FROM publications" in s for s in statements), url
