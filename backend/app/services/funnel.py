"""The content funnel: how far the pieces written in a window got, and where
the rest are sitting.

``analytics_service.pipeline`` answers "how many pieces are in each status right
now", which is a snapshot: a review queue of 40 might be 40 pieces from this
morning or 40 that nobody has opened in a month. This answers the funnel
questions instead — of the pieces *written* in the window, how many reached
review, were approved, went out — and names the ones that have stopped moving.

**Reconstructed from state, not from history.** Pulse keeps no status log, so a
piece's furthest stage is read off where it is now, which is sound because the
stages are ordered:

* ``published``, or any piece with a ``published_at`` (archived after going
  out, say), passed every stage;
* ``approved`` and ``failed`` (publishing was attempted) passed review;
* ``review`` reached review;
* ``draft`` is still at the top;
* ``archived`` without a ``published_at`` was **dropped** — rejected in review,
  or withdrawn. Which of the two is not recorded, so they are one number.

A piece moved back from review to draft counts as a draft: the funnel reports
where work *is*, and that piece is not in review any more.

Broken down by where pieces came from (``source.kind``), because a funnel that
blends hand-written pieces with autopilot's is two different funnels averaged
into a number that describes neither.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only, raiseload

from app.models.content import Content, ContentStatus
from app.models.mixins import as_aware, utcnow
from app.models.project import Project

STAGES = ("written", "reached_review", "approved", "published")

#: Where a piece's ``source.kind`` puts it in the breakdown. Anything else —
#: seed data, an old kind — is ``other`` rather than its own row.
_ORIGINS = {
    "manual": "manual",
    "calendar_manual": "manual",
    "autopilot": "autopilot",
    "release": "autopilot",
    "manual_refresh": "autopilot",
    "trigger": "trigger",
    "template": "template",
    "idea": "idea",
    "api_key": "api",
}

#: Sitting still longer than this, in draft or review, is "stuck".
DEFAULT_STALE_DAYS = 7


def _furthest(content: Content) -> str:
    if content.published_at is not None or content.status == ContentStatus.PUBLISHED:
        return "published"
    if content.status in (ContentStatus.APPROVED, ContentStatus.FAILED):
        return "approved"
    if content.status == ContentStatus.REVIEW:
        return "reached_review"
    if content.status == ContentStatus.ARCHIVED:
        return "dropped"
    return "written"


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _empty() -> dict[str, int]:
    return {stage: 0 for stage in STAGES} | {"dropped": 0}


def _cumulate(counts: dict[str, int]) -> dict:
    """Turn "furthest stage reached" counts into the funnel's cumulative steps."""
    published = counts["published"]
    approved = counts["approved"] + published
    reviewed = counts["reached_review"] + approved
    written = counts["written"] + reviewed + counts["dropped"]
    return {
        "written": written,
        "reached_review": reviewed,
        "approved": approved,
        "published": published,
        "dropped": counts["dropped"],
        "review_rate": _rate(reviewed, written),
        "approval_rate": _rate(approved, reviewed),
        "publish_rate": _rate(published, approved),
        "overall_rate": _rate(published, written),
    }


def funnel(
    db: Session, user_id: int, *, days: int, stale_days: int = DEFAULT_STALE_DAYS
) -> dict:
    """The funnel for pieces written in the last *days*, overall and per origin,
    with the pieces stuck in draft or review for over *stale_days*."""
    now = utcnow()
    since = now - timedelta(days=days)
    rows = db.scalars(
        select(Content)
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user_id, Content.created_at >= since)
        # The columns this reads and no more. A whole row carries the body —
        # up to 200,000 characters a piece — and ``publications`` is
        # ``selectin``, so a 90-day window loaded every body and every
        # publication row just to look at a status and a source (C104 M8).
        .options(
            load_only(
                Content.id,
                Content.title,
                Content.status,
                Content.source,
                Content.created_at,
                Content.updated_at,
                Content.published_at,
            ),
            raiseload(Content.publications),
        )
    ).all()

    overall = _empty()
    by_origin: dict[str, dict[str, int]] = defaultdict(_empty)
    hours_to_publish: list[float] = []
    stuck: list[dict] = []
    stale_before = now - timedelta(days=stale_days)

    for content in rows:
        stage = _furthest(content)
        origin = _ORIGINS.get(str((content.source or {}).get("kind") or ""), "other")
        overall[stage] += 1
        by_origin[origin][stage] += 1

        created = as_aware(content.created_at)
        if content.published_at is not None:
            hours = (as_aware(content.published_at) - created).total_seconds() / 3600
            hours_to_publish.append(max(0.0, hours))
        if stage in ("written", "reached_review"):
            # How long it has sat where it is: the last write moved it there.
            idle_since = as_aware(content.updated_at or content.created_at)
            if idle_since < stale_before:
                stuck.append({
                    "content_id": content.id,
                    "title": content.title,
                    "status": content.status.value,
                    "origin": origin,
                    "idle_days": round((now - idle_since).total_seconds() / 86400, 1),
                })

    stuck.sort(key=lambda s: -s["idle_days"])
    return {
        "days": days,
        "stale_days": stale_days,
        "overall": _cumulate(overall),
        "by_origin": [
            {"origin": origin, **_cumulate(counts)}
            for origin, counts in sorted(by_origin.items(), key=lambda kv: -sum(kv[1].values()))
        ],
        "median_hours_to_publish": (
            round(statistics.median(hours_to_publish), 1) if hours_to_publish else None
        ),
        "stuck_in_draft": sum(1 for s in stuck if s["status"] == ContentStatus.DRAFT.value),
        "stuck_in_review": sum(1 for s in stuck if s["status"] == ContentStatus.REVIEW.value),
        "stuck": stuck[:20],
    }


__all__ = ["DEFAULT_STALE_DAYS", "STAGES", "funnel"]
