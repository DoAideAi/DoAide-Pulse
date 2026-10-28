"""Every breakdown on the analytics page adds up to the headline (C104 M2).

``GET /analytics/overview`` returns totals and four breakdowns of the same
numbers — by content type, by platform, by project, and the top pieces. Each is
computed by its own function from the same pre-fetched set of latest snapshots,
and a mistake in any one shows as a table whose rows do not sum to the number at
the top of the page. The dataset has the cases that break that: several
snapshots of one publication (only the latest counts — counters are
cumulative), one piece on two platforms, a publication that failed, a second
project, a platform reporting no reads, and another account's numbers.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.metrics import ContentMetric
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.publication import Platform, Publication, PublicationStatus

URL = "/api/v1/analytics/overview"


def _piece(db, project, title, content_type=ContentType.ANNOUNCEMENT):
    row = Content(
        project_id=project.id, content_type=content_type, status=ContentStatus.PUBLISHED,
        title=title, slug=title.lower().replace(" ", "-"), body_markdown="word " * 400,
        published_at=utcnow() - timedelta(days=3),
    )
    db.add(row)
    db.flush()
    return row


def _publication(db, content, platform, status=PublicationStatus.PUBLISHED):
    row = Publication(
        content_id=content.id, platform=platform, status=status,
        published_at=utcnow() - timedelta(days=3) if status == PublicationStatus.PUBLISHED else None,
    )
    db.add(row)
    db.flush()
    return row


def _snapshot(db, publication, hours_ago, **counts):
    db.add(ContentMetric(
        publication_id=publication.id, captured_at=utcnow() - timedelta(hours=hours_ago), **counts
    ))


@pytest.fixture
def dataset(db, user, project):
    other_project = Project(user_id=user.id, name="Second", slug="second")
    db.add(other_project)
    db.flush()

    launch = _piece(db, project, "Launch")
    tutorial = _piece(db, project, "Tutorial", ContentType.TUTORIAL)
    second = _piece(db, other_project, "Second project piece")

    devto = _publication(db, launch, Platform.DEVTO)
    # Three readings of one cumulative counter: only the last is the truth.
    _snapshot(db, devto, 48, views=100, reads=40, reactions=5)
    _snapshot(db, devto, 24, views=250, reads=90, reactions=9, comments=1)
    _snapshot(db, devto, 1, views=400, reads=150, reactions=12, comments=3)
    # The same piece on a second platform, which reports no reads at all.
    bluesky = _publication(db, launch, Platform.BLUESKY)
    _snapshot(db, bluesky, 2, views=None, reactions=20, shares=4)

    hashnode = _publication(db, tutorial, Platform.HASHNODE)
    _snapshot(db, hashnode, 3, views=1000, reads=300, reactions=30, comments=7, shares=2)
    # A failed attempt beside it: counts as a failure, carries no reach.
    _publication(db, tutorial, Platform.MEDIUM, PublicationStatus.FAILED)

    medium = _publication(db, second, Platform.MEDIUM)
    _snapshot(db, medium, 5, views=60, reads=20, clicks=6, reactions=2)

    # Another account's post, which must appear nowhere.
    from app.models.user import User
    from app.security import hash_password

    stranger = User(email="stranger@example.com", hashed_password=hash_password("pw-pw-pw-pw"))
    db.add(stranger)
    db.flush()
    theirs = Project(user_id=stranger.id, name="Theirs", slug="theirs")
    db.add(theirs)
    db.flush()
    _snapshot(db, _publication(db, _piece(db, theirs, "Theirs"), Platform.DEVTO), 1, views=99999, reactions=999)
    db.commit()


# The latest snapshot of each of this account's publications. Engagement is
# every interaction reported — reactions, comments, shares and clicks
# (``ContentMetric.engagement``).
EXPECTED_VIEWS = 400 + 0 + 1000 + 60
EXPECTED_ENGAGEMENT = (12 + 3) + (20 + 4) + (30 + 7 + 2) + (2 + 6)


def _sum(rows, key):
    return sum(row[key] or 0 for row in rows)


def test_the_headline_counts_the_latest_snapshot_of_each_publication(client, auth, dataset):
    totals = client.get(URL, headers=auth).json()["totals"]
    assert totals["views"] == EXPECTED_VIEWS
    assert totals["engagement"] == EXPECTED_ENGAGEMENT
    assert totals["publication_count"] == 4  # the failed one is not a publication


@pytest.mark.parametrize("breakdown", ["by_content_type", "by_platform", "by_project", "top_content"])
@pytest.mark.parametrize("key", ["views", "engagement"])
def test_every_breakdown_sums_to_the_headline(client, auth, dataset, breakdown, key):
    body = client.get(URL, headers=auth).json()
    assert _sum(body[breakdown], key) == body["totals"][key], (breakdown, body[breakdown])


def test_a_piece_on_two_platforms_is_one_row_in_top_content(client, auth, dataset):
    top = client.get(URL, headers=auth).json()["top_content"]
    launch = [row for row in top if row["title"] == "Launch"]
    assert len(launch) == 1
    assert launch[0]["views"] == 400
    assert launch[0]["engagement"] == 15 + 24


def test_the_failure_counts_against_its_platform_and_adds_no_reach(client, auth, dataset):
    by_platform = {row["platform"]: row for row in client.get(URL, headers=auth).json()["by_platform"]}
    assert by_platform["medium"]["failed"] == 1
    assert by_platform["medium"]["published"] == 1
    assert by_platform["medium"]["views"] == 60


def test_a_platform_that_reports_no_reads_does_not_drag_the_read_rate_down(client, auth, dataset):
    """Bluesky reports reactions but no views or reads; its absence is not a
    zero, so the read rate is over the platforms that report reads."""
    by_platform = {row["platform"]: row for row in client.get(URL, headers=auth).json()["by_platform"]}
    assert by_platform["bluesky"]["read_rate"] is None
    assert by_platform["devto"]["read_rate"] == pytest.approx(150 / 400, abs=1e-3)
