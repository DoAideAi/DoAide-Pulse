"""Which of Pulse's features an account actually uses.

The browser already records every write it makes as an ``action`` named by
method and route pattern — ``POST /content/:id/headlines/apply`` — and every
page it opens as a ``page_view`` (``frontend/src/lib/activity.js``). Those raw
names answer "which endpoint", which is not the question anyone asks. This maps
them onto the product's features, so the answer to "is anybody using headline
testing?" is a number rather than a grep.

Two features have no browser event to count, and are measured from what they
leave behind instead:

* **Autopilot** writes pieces with nobody in the browser. Its usage is the
  pieces whose ``source.kind`` is ``autopilot`` or ``trigger``.
* Reads (``GET``) are not recorded as actions, so a read-only feature — the
  SEO dashboard, the calendar — is counted by its page views.

The mapping is a table rather than logic so adding a feature is one line, and
an action no feature claims is reported as ``unmapped`` rather than dropped:
the list of unmapped names is what tells you the table has fallen behind.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity import ACTION, PAGE_VIEW, ActivityEvent
from app.models.content import Content
from app.models.mixins import utcnow
from app.models.project import Project


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    #: ``(kind, pattern)`` pairs. ``pattern`` is a full-match regex over the
    #: event name: ``"POST /content/:id/approve"`` for an action, the route
    #: pattern (``"/seo"``) for a page view.
    events: tuple[tuple[str, str], ...]


#: Every feature the analytics page reports on, in the order it shows them.
FEATURES: tuple[Feature, ...] = (
    Feature("projects", "Projects & repo scans", (
        (ACTION, r"(POST|PATCH|DELETE) /projects(/:id)?"),
        (ACTION, r"POST /projects/:id/scan"),
    )),
    Feature("writing", "Writing & editing", (
        (ACTION, r"POST /content"),
        (ACTION, r"(PATCH|DELETE) /content/:id"),
        (ACTION, r"POST /content/:id/revisions/:id/restore"),
        (ACTION, r"POST /tags/rename"),
    )),
    Feature("ai_generation", "AI drafting", (
        (ACTION, r"POST /content/generate"),
        (ACTION, r"POST /content/:id/edit"),
        (ACTION, r"POST /content/:id/repurpose"),
        (ACTION, r"POST /ai/generate-fields"),
        (ACTION, r"POST /projects/draft-from-documents"),
        (ACTION, r"POST /content/ideas/:id/write"),
    )),
    Feature("seo", "SEO tools", (
        (ACTION, r"POST /seo/.*"),
        (ACTION, r"POST /tags/suggest/:id"),
        (PAGE_VIEW, r"/seo"),
    )),
    Feature("review", "Review & approval", (
        (ACTION, r"POST /content/:id/(approve|status)"),
        (ACTION, r"POST /content/bulk/(approve|reject|archive-old)"),
    )),
    Feature("publishing", "Publishing", (
        (ACTION, r"POST /content/:id/publish"),
        (ACTION, r"POST /content/:id/retry(/:id)?"),
        (ACTION, r"POST /content/bulk/(publish|retry)"),
    )),
    Feature("scheduling", "Scheduling & calendar", (
        (ACTION, r"(POST|DELETE) /content/:id/schedule"),
        (ACTION, r"PATCH /calendar/content/:id"),
        (ACTION, r"(POST|PATCH|DELETE) /calendar/ideas(/:id)?"),
        (PAGE_VIEW, r"/calendar"),
    )),
    Feature("headline_testing", "Headline testing", (
        (ACTION, r"POST /content/:id/headlines(/apply|/auto-select)?"),
    )),
    Feature("translation", "Translation", (
        (ACTION, r"(POST|DELETE) /content/:id/translations(/[a-z-]+)?"),
    )),
    Feature("templates", "Templates", (
        (ACTION, r"(POST|PATCH|DELETE) /templates(/:id)?(/use|/preview)?"),
    )),
    Feature("triggers", "Triggers", (
        (ACTION, r"(POST|PATCH|DELETE) /triggers(/:id)?(/check|/rotate-secret)?"),
    )),
    Feature("preview_links", "Preview links", (
        (ACTION, r"(POST|DELETE) /content/:id/preview-links(/:id)?"),
    )),
    Feature("integrations", "Connections, keys & webhooks", (
        (ACTION, r"(PUT|DELETE) /settings/connections(/[a-z]+)?"),
        (ACTION, r"(PUT|DELETE) /settings/llm-key"),
        (ACTION, r"POST /settings/connections/[a-z]+/verify"),
        (ACTION, r"(POST|PATCH|DELETE) /webhooks(/:id)?(/.*)?"),
        (ACTION, r"(POST|DELETE) /api-keys(/:id)?(/rotate)?"),
    )),
)

#: The feature measured from content rather than clicks.
AUTOPILOT_KEY = "autopilot"
_AUTOMATIC_SOURCES = ("autopilot", "trigger")

_COMPILED = [
    (feature, [(kind, re.compile(pattern)) for kind, pattern in feature.events])
    for feature in FEATURES
]


def feature_for(kind: str, name: str) -> str | None:
    """The key of the feature an event belongs to, or ``None``."""
    for feature, patterns in _COMPILED:
        for event_kind, pattern in patterns:
            if kind == event_kind and pattern.fullmatch(name):
                return feature.key
    return None


def usage(db: Session, user_id: int, *, days: int) -> dict:
    """How much each feature was used in the last *days*, most-used first.

    ``uses`` is events (or, for autopilot, pieces written); ``active_days`` is
    the number of distinct days it was used, which separates a feature somebody
    leans on weekly from one they clicked forty times in one afternoon.
    """
    since = utcnow() - timedelta(days=days)
    day = func.date(ActivityEvent.created_at)
    rows = db.execute(
        select(ActivityEvent.kind, ActivityEvent.name, day, func.count())
        .where(ActivityEvent.user_id == user_id, ActivityEvent.created_at >= since)
        .group_by(ActivityEvent.kind, ActivityEvent.name, day)
    ).all()

    uses: dict[str, int] = defaultdict(int)
    days_used: dict[str, set] = defaultdict(set)
    unmapped: dict[str, int] = defaultdict(int)
    for kind, name, when, count in rows:
        key = feature_for(kind, name)
        if key is None:
            if kind == ACTION:
                unmapped[name] += int(count)
            continue
        uses[key] += int(count)
        days_used[key].add(str(when))

    auto_day = func.date(Content.created_at)
    auto_rows = db.execute(
        select(auto_day, func.count())
        .join(Project, Project.id == Content.project_id)
        .where(
            Project.user_id == user_id,
            Content.created_at >= since,
            Content.source["kind"].as_string().in_(_AUTOMATIC_SOURCES),
        )
        .group_by(auto_day)
    ).all()
    for when, count in auto_rows:
        uses[AUTOPILOT_KEY] += int(count)
        days_used[AUTOPILOT_KEY].add(str(when))

    labels = {f.key: f.label for f in FEATURES} | {AUTOPILOT_KEY: "Autopilot & triggers"}
    features = [
        {
            "feature": key,
            "label": label,
            "uses": uses.get(key, 0),
            "active_days": len(days_used.get(key, ())),
        }
        for key, label in labels.items()
    ]
    features.sort(key=lambda f: (-f["uses"], f["label"]))
    return {
        "days": days,
        "features": features,
        "unused": [f["feature"] for f in features if f["uses"] == 0],
        "unmapped_actions": [
            {"name": name, "count": count}
            for name, count in sorted(unmapped.items(), key=lambda kv: -kv[1])[:20]
        ],
    }


__all__ = ["AUTOPILOT_KEY", "FEATURES", "feature_for", "usage"]
