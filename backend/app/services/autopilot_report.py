"""How well the autopilot's gates are judging: what it published unreviewed,
what it held back and why, and how often a person disagreed afterwards.

Every piece ``content_pipeline.generate_and_route`` writes carries its gate
results in ``content.source`` (scores, dead links, duplicate, unsupported
names…) and, since C103 M15, the decision itself under ``routing``:
``{"mode", "candidate", "auto"}``. Older pieces have the evidence but not the
decision; for those it is inferred — APPROVED-or-later with no hold evidence
counts as auto — and the count of inferred pieces is reported, so a number
resting on guesses says so.

The two disagreement measures, read in opposite directions:

* **Overruled holds** — a held piece that a person published anyway. A high
  rate means the gates are stricter than the people reviewing behind them.
* **Pulled auto-publishes** — an auto-approved piece later archived without
  going out. A high rate means the gates are too lenient.

And the place autopilot itself sets a score aside: the SEO gate is waived for a
piece the model is confident in (``docs/BUSINESS_LOGIC.md`` §1, gate 2), so
**auto-approved below the SEO bar** counts how often that waiver was used.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.content import Content, ContentStatus
from app.models.mixins import utcnow
from app.models.project import Project
from app.services import seo

#: Why a held piece was held, in the order the pipeline checks. A piece held by
#: several gates counts under each.
HOLD_REASONS = (
    "not_eligible",
    "dead_links",
    "seo_score",
    "seo_errors",
    "garbled",
    "unsupported_names",
    "duplicate",
    "quality",
)

_QUALITY_BUCKETS = ((0, 39), (40, 59), (60, 79), (80, 100))


def _routed(source: dict) -> bool:
    """Written by ``generate_and_route``, so it has gate results to read."""
    return "routing" in source or "seo_score" in source


def _evidence(source: dict, auto_approvable: bool) -> list[str]:
    """The gates this piece's recorded results would fail."""
    reasons = []
    if source.get("dead_links"):
        reasons.append("dead_links")
    score = source.get("seo_score")
    if score is not None and score < seo.SEO_SCORE_THRESHOLD and not auto_approvable:
        reasons.append("seo_score")
    if source.get("seo_errors"):
        reasons.append("seo_errors")
    if source.get("garbled_runs"):
        reasons.append("garbled")
    if source.get("unsupported_names"):
        reasons.append("unsupported_names")
    if source.get("duplicate_of"):
        reasons.append("duplicate")
    floor = settings.autopilot_auto_publish_min_quality
    quality = source.get("quality_score")
    if floor > 0 and quality is not None and quality < floor:
        reasons.append("quality")
    return reasons


def _decision(content: Content) -> tuple[bool, list[str], bool]:
    """``(auto, hold_reasons, inferred)`` for one routed piece."""
    source = content.source or {}
    auto_approvable = (
        not source.get("fallback")
        and (content.confidence or 0) >= settings.autopilot_auto_approve_confidence
    )
    reasons = _evidence(source, auto_approvable)
    routing = source.get("routing")
    if isinstance(routing, dict) and "auto" in routing:
        auto = bool(routing["auto"])
        if not auto and not routing.get("candidate"):
            reasons.insert(0, "not_eligible")
        return auto, ([] if auto else reasons), False
    # Before the decision was recorded: a piece past review with nothing
    # against it went through on its own; anything else was held.
    past_review = content.published_at is not None or content.status in (
        ContentStatus.APPROVED, ContentStatus.PUBLISHED, ContentStatus.FAILED,
    )
    auto = past_review and not reasons
    if not auto and not reasons:
        reasons = ["not_eligible"]
    return auto, ([] if auto else reasons), True


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def report(db: Session, user_id: int, *, days: int) -> dict:
    """Autopilot's decisions on pieces written in the last *days*."""
    since = utcnow() - timedelta(days=days)
    rows = db.scalars(
        select(Content)
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user_id, Content.created_at >= since)
    ).all()

    auto_n = held_n = inferred = 0
    overruled = pulled = rejected = seo_waived = 0
    reasons: Counter[str] = Counter()
    quality = {"auto": [], "held": []}
    buckets = {f"{lo}-{hi}": {"auto": 0, "held": 0} for lo, hi in _QUALITY_BUCKETS}

    for content in rows:
        source = content.source or {}
        if not _routed(source):
            continue
        auto, why, guessed = _decision(content)
        inferred += guessed
        went_out = content.published_at is not None
        dropped = content.status == ContentStatus.ARCHIVED and not went_out
        side = "auto" if auto else "held"
        if auto:
            auto_n += 1
            pulled += dropped
            score = source.get("seo_score")
            if score is not None and score < seo.SEO_SCORE_THRESHOLD:
                seo_waived += 1
        else:
            held_n += 1
            reasons.update(why)
            overruled += went_out
            rejected += dropped
        q = source.get("quality_score")
        if isinstance(q, (int, float)):
            quality[side].append(float(q))
            for lo, hi in _QUALITY_BUCKETS:
                if lo <= q <= hi:
                    buckets[f"{lo}-{hi}"][side] += 1
                    break

    routed = auto_n + held_n
    return {
        "days": days,
        "routed": routed,
        "auto_approved": auto_n,
        "held": held_n,
        "auto_rate": _rate(auto_n, routed),
        "inferred": inferred,
        "hold_reasons": [
            {"reason": reason, "count": reasons[reason]}
            for reason in HOLD_REASONS
            if reasons[reason]
        ],
        "held_published": overruled,
        "override_rate": _rate(overruled, held_n),
        "held_rejected": rejected,
        "rejection_rate": _rate(rejected, held_n),
        "auto_pulled": pulled,
        "pulled_rate": _rate(pulled, auto_n),
        "auto_below_seo_threshold": seo_waived,
        "median_quality_auto": _median(quality["auto"]),
        "median_quality_held": _median(quality["held"]),
        "quality_distribution": [
            {"bucket": bucket, **counts} for bucket, counts in buckets.items()
        ],
    }


__all__ = ["HOLD_REASONS", "report"]
