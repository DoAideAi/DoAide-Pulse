"""Recording, summarising and purging :class:`app.models.activity.ActivityEvent`."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity import ACTION, PAGE_VIEW, ActivityEvent
from app.models.mixins import utcnow


def record(db: Session, user_id: int, events: Iterable[dict]) -> int:
    """Append *events* for *user_id*. Commits. Returns how many were written.

    Each event is ``{"kind", "name", "path"}``, already validated by the schema.
    The timestamp is the server's, not the browser's: a client clock is
    whatever the laptop says, and a summary grouped by day cannot be built on
    that.
    """
    rows = [
        ActivityEvent(
            user_id=user_id,
            kind=event["kind"],
            name=event["name"],
            path=event.get("path"),
        )
        for event in events
    ]
    db.add_all(rows)
    db.commit()
    return len(rows)


def summary(db: Session, user_id: int, *, days: int, limit: int = 10) -> dict:
    """Most-visited pages, most-taken actions and a per-day count, for *days*."""
    since = utcnow() - timedelta(days=days)
    window = (ActivityEvent.user_id == user_id) & (ActivityEvent.created_at >= since)

    def _top(kind: str) -> list[dict]:
        count = func.count(ActivityEvent.id)
        rows = db.execute(
            select(ActivityEvent.name, count)
            .where(window, ActivityEvent.kind == kind)
            .group_by(ActivityEvent.name)
            .order_by(count.desc(), ActivityEvent.name)
            .limit(limit)
        ).all()
        return [{"name": name, "count": int(n)} for name, n in rows]

    # Counted by the database, one row per day and kind. This read every event
    # in the window back to Python — up to 180 days of an account's page views
    # — to make a few dozen numbers, on the theory that SQLite and PostgreSQL
    # cannot agree on truncating a timestamp. ``func.date`` works on both
    # (``feature_usage`` groups by it); SQLite hands back a string and
    # PostgreSQL a date, and ``str`` makes both the ISO day.
    day = func.date(ActivityEvent.created_at)
    per_day: dict[str, dict[str, int]] = {}
    for kind, when, n in db.execute(
        select(ActivityEvent.kind, day, func.count(ActivityEvent.id))
        .where(window)
        .group_by(ActivityEvent.kind, day)
    ):
        bucket = per_day.setdefault(str(when), {PAGE_VIEW: 0, ACTION: 0})
        bucket[kind] = bucket.get(kind, 0) + int(n)

    return {
        "days": days,
        "page_views": sum(b[PAGE_VIEW] for b in per_day.values()),
        "actions": sum(b[ACTION] for b in per_day.values()),
        "top_pages": _top(PAGE_VIEW),
        "top_actions": _top(ACTION),
        "by_day": [
            {"date": date, "page_views": b[PAGE_VIEW], "actions": b[ACTION]}
            for date, b in sorted(per_day.items())
        ],
    }


def purge(db: Session, *, days: int) -> int:
    """Delete activity rows older than *days*. Commits. Returns the row count."""
    cutoff = utcnow() - timedelta(days=days)
    deleted = db.execute(
        ActivityEvent.__table__.delete().where(ActivityEvent.created_at < cutoff)
    ).rowcount
    db.commit()
    return int(deleted or 0)


__all__ = ["purge", "record", "summary"]
