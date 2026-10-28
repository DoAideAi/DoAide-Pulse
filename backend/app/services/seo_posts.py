"""SEO blog posts: ordinary :class:`Content` rows carrying the ``seo`` tag.

Not a second content model. An SEO post is written, scheduled and published
exactly like any other piece — the same editor checks, the same SEO preflight,
the same cadence-driven ``optimize`` slot picker and the same adapters — so the
SEO page is a focused front door onto that pipeline, and this module only adds
what the pipeline does not already know:

* which pieces are the SEO ones (:data:`SEO_TAG`), for the queue and calendar;
* internal-link suggestions that reach *across* projects and out to the DoAide
  product sites, where the content router's suggestions stay inside one project.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content import Content, ContentStatus
from app.models.mixins import as_aware
from app.models.project import Project
from app.services import seo
from app.services.seo_sites import SITES

SEO_TAG = "seo"
#: How many of the account's pieces are considered when looking for SEO ones
#: or link targets. Selected as narrow columns, so this bounds rows, not bodies.
CANDIDATE_LIMIT = 500


def _mentions(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text) is not None


def product_links(
    *, title: str, body_markdown: str, keywords: list[str], limit: int = 4
) -> list[dict]:
    """DoAide product sites this draft is about, best match first.

    A topic counts when it is one of the draft's keywords or appears in its
    title or text. Sites the body already links to are left out — the
    suggestion is for a link the author has not made yet.
    """
    text = f"{title}\n{seo.strip_markdown(body_markdown)}".lower()
    own = {k.strip().lower() for k in keywords if k and k.strip()}
    linked = body_markdown.lower()
    out = []
    for site in SITES:
        if site.domain in linked:
            continue
        matched = sorted(t for t in site.topics if t in own or _mentions(text, t))
        if not matched:
            continue
        # A keyword match is the author saying "this is what the post is
        # about"; a mention in passing counts for less.
        score = sum(2 if t in own else 1 for t in matched)
        out.append(
            {
                "site_key": site.key,
                "name": site.name,
                "url": site.url,
                "anchor": matched[0],
                "matched_topics": matched,
                "score": score,
            }
        )
    out.sort(key=lambda d: (-d["score"], d["name"]))
    return out[:limit]


def post_links(
    db: Session,
    user_id: int,
    *,
    keywords: list[str],
    focus_keyword: str,
    exclude_content_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """The account's published posts worth linking to, from any project."""
    query = (
        select(
            Content.id,
            Content.title,
            Content.slug,
            Content.keywords,
            Content.focus_keyword,
            Content.canonical_url,
        )
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user_id, Content.status == ContentStatus.PUBLISHED)
        .order_by(Content.created_at.desc())
        .limit(CANDIDATE_LIMIT)
    )
    if exclude_content_id is not None:
        query = query.where(Content.id != exclude_content_id)
    rows = db.execute(query).all()
    return seo.suggest_internal_links(
        keywords=keywords,
        focus_keyword=focus_keyword,
        candidates=[
            {
                "content_id": r.id,
                "title": r.title,
                "slug": r.slug,
                "keywords": r.keywords,
                "focus_keyword": r.focus_keyword,
                "canonical_url": r.canonical_url,
            }
            for r in rows
        ],
        limit=limit,
    )


def queue(db: Session, user_id: int, *, limit: int = 100) -> list[dict]:
    """The account's SEO posts: scheduled soonest first, then the rest newest first."""
    rows = db.execute(
        select(
            Content.id,
            Content.title,
            Content.slug,
            Content.status,
            Content.tags,
            Content.focus_keyword,
            Content.keywords,
            Content.meta_description,
            Content.scheduled_for,
            Content.published_at,
            Content.created_at,
            Content.word_count,
            Project.name.label("project_name"),
        )
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user_id, Content.status != ContentStatus.ARCHIVED)
        .order_by(Content.created_at.desc())
        .limit(CANDIDATE_LIMIT)
    ).all()
    posts = [
        {
            "id": r.id,
            "title": r.title,
            "slug": r.slug,
            "status": r.status.value if hasattr(r.status, "value") else r.status,
            "project_name": r.project_name,
            "focus_keyword": r.focus_keyword,
            "keywords": r.keywords or [],
            "meta_description_length": len(r.meta_description or ""),
            "word_count": r.word_count,
            "scheduled_for": as_aware(r.scheduled_for) if r.scheduled_for else None,
            "published_at": as_aware(r.published_at) if r.published_at else None,
            "created_at": as_aware(r.created_at),
        }
        for r in rows
        if SEO_TAG in (t.lower() for t in r.tags or [])
    ]
    upcoming = sorted(
        (p for p in posts if p["scheduled_for"] and not p["published_at"]),
        key=lambda p: p["scheduled_for"],
    )
    # By id: ``p not in upcoming`` was a list scan per post, each step a dict
    # comparison — quadratic in the 500 candidates for an answer a set gives
    # in one pass.
    scheduled = {p["id"] for p in upcoming}
    rest = [p for p in posts if p["id"] not in scheduled]
    return (upcoming + rest)[:limit]
