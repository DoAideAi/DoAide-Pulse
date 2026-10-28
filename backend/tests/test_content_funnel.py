"""The content funnel: how far the pieces written in a window got.

Pulse keeps no status history, so ``GET /analytics/funnel`` reads each piece's
furthest stage off its current state. These pin that reading, the per-origin
split, and what counts as stuck.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow

URL = "/api/v1/analytics/funnel"


def _piece(db, project, n, status, kind="manual", *, published=False, age_days=0):
    when = utcnow() - timedelta(days=age_days)
    content = Content(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT, status=status,
        title=f"P{n}", slug=f"p{n}", body_markdown="b", source={"kind": kind},
        created_at=when, updated_at=when,
        published_at=when + timedelta(hours=6) if published else None,
    )
    db.add(content)
    return content


def test_each_piece_counts_at_every_stage_it_passed(client, auth, db, project):
    _piece(db, project, 1, ContentStatus.DRAFT)
    _piece(db, project, 2, ContentStatus.REVIEW)
    _piece(db, project, 3, ContentStatus.APPROVED)
    _piece(db, project, 4, ContentStatus.FAILED)
    _piece(db, project, 5, ContentStatus.PUBLISHED, published=True)
    # Archived after going out: still published.
    _piece(db, project, 6, ContentStatus.ARCHIVED, published=True)
    # Archived without going out: dropped.
    _piece(db, project, 7, ContentStatus.ARCHIVED)
    db.commit()

    overall = client.get(URL, headers=auth).json()["overall"]

    assert overall["written"] == 7
    assert overall["reached_review"] == 5
    assert overall["approved"] == 4
    assert overall["published"] == 2
    assert overall["dropped"] == 1
    assert overall["publish_rate"] == 0.5
    assert overall["overall_rate"] == round(2 / 7, 4)


def test_the_funnel_is_split_by_origin(client, auth, db, project):
    _piece(db, project, 1, ContentStatus.PUBLISHED, "autopilot", published=True)
    _piece(db, project, 2, ContentStatus.REVIEW, "autopilot")
    _piece(db, project, 3, ContentStatus.DRAFT, "calendar_manual")
    _piece(db, project, 4, ContentStatus.DRAFT, "seed")
    db.commit()

    body = client.get(URL, headers=auth).json()
    by_origin = {row["origin"]: row for row in body["by_origin"]}

    assert by_origin["autopilot"]["written"] == 2
    assert by_origin["autopilot"]["published"] == 1
    assert by_origin["manual"]["written"] == 1
    assert by_origin["other"]["written"] == 1
    assert body["by_origin"][0]["origin"] == "autopilot"
    assert body["median_hours_to_publish"] == 6.0


def test_pieces_idle_in_draft_or_review_are_stuck(client, auth, db, project):
    _piece(db, project, 1, ContentStatus.DRAFT, age_days=20)
    _piece(db, project, 2, ContentStatus.REVIEW, age_days=10)
    _piece(db, project, 3, ContentStatus.REVIEW, age_days=1)
    # Old but approved: waiting on a schedule, not stuck in the funnel.
    _piece(db, project, 4, ContentStatus.APPROVED, age_days=30)
    db.commit()

    body = client.get(URL, headers=auth, params={"stale_days": 7}).json()

    assert body["stuck_in_draft"] == 1
    assert body["stuck_in_review"] == 1
    assert [s["title"] for s in body["stuck"]] == ["P1", "P2"]
    assert body["stuck"][0]["idle_days"] >= 19.9


def test_the_window_and_the_account_bound_the_funnel(client, auth, db, project):
    from app.models.project import Project
    from app.models.user import User
    from app.security import hash_password

    _piece(db, project, 1, ContentStatus.DRAFT, age_days=200)
    other = User(email="o@example.com", hashed_password=hash_password("pw12345678"))
    db.add(other)
    db.commit()
    theirs = Project(user_id=other.id, name="Theirs", slug="theirs")
    db.add(theirs)
    db.commit()
    _piece(db, theirs, 2, ContentStatus.DRAFT)
    db.commit()

    body = client.get(URL, headers=auth, params={"days": 90}).json()

    assert body["overall"]["written"] == 0
    assert body["overall"]["review_rate"] is None
    assert body["by_origin"] == []
    assert body["median_hours_to_publish"] is None
