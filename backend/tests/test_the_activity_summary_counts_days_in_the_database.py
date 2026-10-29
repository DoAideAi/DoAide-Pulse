"""The activity summary counts each day in the database, not row by row in Python.

``activity.summary`` built its per-day series by reading every event in the
window back to Python — up to 180 days of page views and actions, tens of
thousands of rows on an active account — to turn into a few dozen numbers.
The reason given was that SQLite and PostgreSQL disagree about truncating a
timestamp; ``feature_usage`` already groups by ``func.date`` on both.

It now asks for one row per day and kind. The answer is unchanged.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.activity import ActivityEvent
from app.models.mixins import utcnow
from app.services import activity


def _events(db, user, days_back: int, kind: str, n: int) -> None:
    when = utcnow() - timedelta(days=days_back)
    db.add_all(
        ActivityEvent(user_id=user.id, kind=kind, name="/content", created_at=when)
        for _ in range(n)
    )


def test_the_series_is_unchanged(db, user):
    _events(db, user, 1, activity.PAGE_VIEW, 5)
    _events(db, user, 1, activity.ACTION, 2)
    _events(db, user, 3, activity.PAGE_VIEW, 4)
    db.commit()

    result = activity.summary(db, user.id, days=30)

    assert result["page_views"] == 9
    assert result["actions"] == 2
    by_day = {row["date"]: (row["page_views"], row["actions"]) for row in result["by_day"]}
    day1 = (utcnow() - timedelta(days=1)).date().isoformat()
    day3 = (utcnow() - timedelta(days=3)).date().isoformat()
    assert by_day == {day1: (5, 2), day3: (4, 0)}


def test_no_query_reads_the_events_one_row_each(db, user, sql_log):
    _events(db, user, 1, activity.PAGE_VIEW, 40)
    db.commit()
    sql_log.clear()

    activity.summary(db, user.id, days=30)

    reads = [s for s in sql_log if s.startswith("SELECT") and "FROM activity_events" in s]
    assert reads
    assert all("GROUP BY" in s for s in reads), reads
