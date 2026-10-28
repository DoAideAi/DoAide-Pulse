"""Subscriber growth reaches the dashboard as counts, never as addresses.

The embed widget collects emails unauthenticated (``POST /viral/subscribers``)
and until now the table was write-only: nothing in the product ever showed the
user that anyone had signed up. ``GET /analytics/subscribers`` closes that loop
with four shapes — a total, a 30-day count, a zero-filled per-day series whose
cumulative edge equals the total, and a per-source breakdown — and none of them
may carry an address.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import settings
from app.models.mixins import utcnow
from app.models.subscriber import Subscriber


@pytest.fixture(autouse=True)
def _single_user_install(monkeypatch):
    """The install as shipped: registration closed, so the one account runs it
    and sees the unattributed widget sign-ups too. The multi-account rule is
    pinned in test_subscriber_counts_stay_with_their_account.py."""
    monkeypatch.setattr(settings, "registration_enabled", False)
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")


def _seed(db, project, *, days_ago_counts: dict[int, int]) -> int:
    """Insert subscribers created N days ago; returns how many in all."""
    now = utcnow()
    total = 0
    for days_ago, count in days_ago_counts.items():
        for i in range(count):
            sub = Subscriber(
                email=f"reader{days_ago}-{i}@example.com",
                source="embed" if i % 2 == 0 else "article",
                project_id=project.id if i % 3 == 0 else None,
            )
            db.add(sub)
            db.flush()
            # TimestampMixin stamps "now"; the series needs history.
            sub.created_at = now - timedelta(days=days_ago)
            total += 1
    db.commit()
    return total


def test_totals_series_and_sources_agree(client, auth, db, project):
    total = _seed(db, project, days_ago_counts={0: 2, 3: 1, 45: 3})

    body = client.get("/api/v1/analytics/subscribers", headers=auth).json()

    assert body["total"] == total
    assert body["last_30_days"] == 3  # the two today + one three days ago
    assert sum(p["count"] for p in body["series"]) == total  # 45 < 90-day window
    assert body["series"][-1]["cumulative"] == total
    assert sum(row["count"] for row in body["by_source"]) == total


def test_the_series_has_no_gaps_and_the_edge_carries_history(client, auth, db, project):
    _seed(db, project, days_ago_counts={200: 4, 1: 1})

    body = client.get("/api/v1/analytics/subscribers", headers=auth, params={"days": 7}).json()

    # Eight calendar days (window start through today), every one present.
    assert len(body["series"]) == 8
    assert {p["count"] for p in body["series"][:-2]} == {0}
    # The 4 sign-ups from before the window are in the baseline, not dropped.
    assert body["series"][0]["cumulative"] == 4
    assert body["series"][-1]["cumulative"] == body["total"] == 5


def test_no_address_leaves_the_table(client, auth, db, project):
    _seed(db, project, days_ago_counts={0: 1})

    body = client.get("/api/v1/analytics/subscribers", headers=auth).json()

    assert "@" not in str(body)


def test_another_users_project_subscribers_stay_theirs(client, auth, db, project):
    """Project-attributed sign-ups are scoped. Unattributed ones go to the
    install's operator, which on a single-user install is this account."""
    from app.models.project import Project
    from app.models.user import User
    from app.security import hash_password

    other = User(email="other@example.com", hashed_password=hash_password("pw12345678"))
    db.add(other)
    db.flush()
    theirs = Project(user_id=other.id, name="Theirs", slug="theirs", description="x")
    db.add(theirs)
    db.flush()
    db.add(Subscriber(email="their-reader@example.com", source="embed", project_id=theirs.id))
    db.add(Subscriber(email="shared-reader@example.com", source="embed", project_id=None))
    db.commit()

    body = client.get("/api/v1/analytics/subscribers", headers=auth).json()

    assert body["total"] == 1  # the unattributed one; not the other user's


def test_the_response_model_does_not_drop_fields(client, auth, db, user, project):
    """The same key diff the other analytics payloads get (see
    test_analytics_response_models.py): a field the model forgets is a field
    the API silently stops returning."""
    from app.services import analytics_service

    _seed(db, project, days_ago_counts={0: 1, 10: 2})

    produced = analytics_service.subscriber_growth(db, user.id)
    answered = client.get("/api/v1/analytics/subscribers", headers=auth).json()

    assert set(answered) == set(produced)
    assert set(answered["series"][0]) == set(produced["series"][0])
    assert set(answered["by_source"][0]) == set(produced["by_source"][0])


def test_the_counts_are_one_scan_not_three(client, auth, db, project, sql_log):
    """Total, last-30 and before-window share their WHERE clause; they were
    three separate passes over the subscriber table on every page load."""
    _seed(db, project, days_ago_counts={0: 2, 40: 1, 200: 1})

    sql_log.clear()
    body = client.get("/api/v1/analytics/subscribers", headers=auth).json()

    assert (body["total"], body["last_30_days"]) == (4, 2)
    assert body["series"][0]["cumulative"] == 1  # the 200-day-old one
    scans = [s for s in sql_log if s.startswith("SELECT") and "FROM subscribers" in s]
    # One for the counts, one for the per-day series, one for the sources.
    assert len(scans) == 3, "\n".join(s[:160] for s in scans)
