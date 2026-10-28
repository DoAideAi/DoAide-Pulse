"""Public-facing viral features: shareable articles, subscriber collection,
and the free content idea generator."""
from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, lazyload

from app.config import settings
from app.database import get_db
from app.models.content import Content, ContentStatus
from app.models.project import Project
from app.models.subscriber import Subscriber
from app.ratelimit import limiter
from app.schemas.errors import ErrorOut, errors
from app.schemas.viral import (
    ContentIdeaItem,
    ContentIdeasIn,
    ContentIdeasOut,
    PublicArticleOut,
    SubscribeIn,
    SubscribeOut,
    UnsubscribeIn,
)
from app.services.breaker import CircuitBreaker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["viral"])

#: Gemini for the free idea generator, which calls it directly rather than
#: through ``llm_router`` and so had no breaker of its own. Without one, an
#: outage cost every anonymous caller the full 30-second timeout on a worker
#: thread — and sync routes share one pool, so a few IPs inside their own rate
#: limit were enough to queue up the whole API behind a provider that was down.
#: Counts transport and HTTP failures only: an unparseable answer comes back
#: fast and holds nothing.
idea_breaker = CircuitBreaker(threshold=3, cooldown_seconds=60.0)
_IDEA_BREAKER_KEY = "gemini"


@router.get(
    "/articles/{slug}",
    response_model=PublicArticleOut,
    summary="A published article, publicly accessible",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorOut,
            "description": "No published article with this slug.",
        },
        **errors(status.HTTP_429_TOO_MANY_REQUESTS),
    },
)
@limiter.limit(settings.rate_limit_public_read)
def get_public_article(
    request: Request,
    response: Response,
    slug: str = Path(max_length=320),
    db: Session = Depends(get_db),
) -> PublicArticleOut:
    """Fetch a published article by slug. Unauthenticated."""
    logger.debug("article view: slug=%s", slug)
    # One statement. Plain ``select(Content)`` was three on the page every
    # shared link lands on: the row, then the ``lazy="selectin"`` publications
    # this response never reads, then a lazy load of the project for its name.
    content = db.scalar(
        select(Content)
        .options(
            lazyload(Content.publications),
            joinedload(Content.project).load_only(Project.name),
        )
        .where(
            Content.slug == slug,
            Content.status == ContentStatus.PUBLISHED,
        )
        # Slugs are unique per project, not across Pulse, so two projects —
        # two accounts, even — can both have a published ``hello-world``.
        # Unordered, which one this URL showed was up to the planner and could
        # change between requests; a newer piece by somebody else could take
        # over a link that had been shared for months. The first to publish
        # keeps it.
        .order_by(Content.published_at.asc().nulls_last(), Content.id.asc())
        .limit(1)
    )
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found.",
        )
    return PublicArticleOut(
        title=content.title,
        slug=content.slug,
        body_markdown=content.body_markdown,
        excerpt=content.excerpt,
        cover_image_url=content.cover_image_url,
        meta_description=content.meta_description,
        tags=content.tags,
        word_count=content.word_count,
        read_minutes=content.read_minutes,
        project_name=content.project.name if content.project else None,
        published_at=content.published_at,
    )


@router.post(
    "/subscribers",
    response_model=SubscribeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Collect a newsletter subscriber email",
    responses=errors(status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit("10/minute;100/hour")
def subscribe(
    request: Request,
    response: Response,
    payload: SubscribeIn,
    db: Session = Depends(get_db),
) -> SubscribeOut:
    """Collect an email from the embed widget or public pages. Unauthenticated.

    One row per address *per project*: the same reader signing up on two
    accounts' articles is on both lists. The answer is the same either way,
    so this cannot be used to find out who is already subscribed.
    """
    email = payload.email.lower()
    project_id = _article_project(db, payload.article)
    if project_id is None and db.scalar(
        select(Subscriber.id).where(
            Subscriber.email == email, Subscriber.project_id.is_(None)
        )
    ):
        # The unique constraint cannot see this one — NULLs never collide —
        # so an unattributed repeat is caught here. Logged like the other
        # duplicate below: this branch was the one silent way to subscribe.
        logger.debug("duplicate subscriber ignored: source=%s", payload.source or "direct")
        return SubscribeOut(ok=True)
    sub = Subscriber(email=email, source=payload.source, project_id=project_id)
    db.add(sub)
    try:
        db.commit()
        logger.info("new subscriber: source=%s", payload.source or "direct")
    except IntegrityError:
        db.rollback()
        # Not the address: a subscriber list is PII, and the log is not where it lives.
        logger.debug("duplicate subscriber ignored: source=%s", payload.source or "direct")
    return SubscribeOut(ok=True)


@router.post(
    "/subscribers/unsubscribe",
    response_model=SubscribeOut,
    summary="Take an email off the newsletter list",
    responses=errors(status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit("10/minute;100/hour")
def unsubscribe(
    request: Request,
    response: Response,
    payload: UnsubscribeIn,
    db: Session = Depends(get_db),
) -> SubscribeOut:
    """Delete the address, outright. Unauthenticated, like subscribing.

    Deleted rather than flagged: Pulse collects the address and does nothing
    else with it — no list it is shown on, no mail it is sent — so a row kept
    as "unsubscribed" would be the same personal data held for no purpose,
    and withdrawing consent is the reason to have this at all.

    The same answer whether or not the address was on the list, so this
    cannot be used to find out who subscribed.
    """
    result = db.execute(delete(Subscriber).where(Subscriber.email == payload.email.lower()))
    db.commit()
    # A count, not the address: the log is not where the list lives.
    logger.info("unsubscribe: %d row(s) removed", result.rowcount or 0)
    return SubscribeOut(ok=True)


def _article_project(db: Session, slug: str | None) -> int | None:
    """The project behind a *published* article slug, or ``None``.

    The same first-published rule as :func:`get_public_article`, so a sign-up
    is attributed to the project whose article the reader was actually shown.
    Anything else — no slug, an unpublished one, a typo — leaves it
    unattributed rather than refusing a reader over an optional field.
    """
    if not slug:
        return None
    return db.scalar(
        select(Content.project_id)
        .where(Content.slug == slug, Content.status == ContentStatus.PUBLISHED)
        .order_by(Content.published_at.asc().nulls_last(), Content.id.asc())
        .limit(1)
    )


_IDEA_TYPES = frozenset(
    {"tutorial", "how_to", "comparison", "announcement", "feature_spotlight", "product_spotlight"}
)


def _idea_text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _parse_ideas(raw: object, count: int) -> list[ContentIdeaItem]:
    """The usable ideas in whatever JSON the model answered with.

    The niche is free text from an anonymous caller, and it goes into the
    prompt, so the shape of the answer is theirs to steer: an object instead of
    an array, a bare string where an idea belongs, a number for a title. Each of
    those was an uncaught ``AttributeError`` or ``ValidationError`` and a 500
    from a public endpoint. Anything that is not an idea is skipped.
    """
    if isinstance(raw, dict):
        raw = raw.get("ideas")
    if not isinstance(raw, list):
        return []
    ideas = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _idea_text(item.get("title"), 300)
        if not title:
            continue
        kind = item.get("content_type")
        ideas.append(
            ContentIdeaItem(
                title=title,
                hook=_idea_text(item.get("hook"), 500),
                content_type=kind if kind in _IDEA_TYPES else "tutorial",
            )
        )
        if len(ideas) == count:
            break
    return ideas


@router.post(
    "/tools/content-ideas",
    response_model=ContentIdeasOut,
    summary="AI-powered content idea generator (free, no login)",
    responses=errors(
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
@limiter.limit("5/minute;30/hour")
def generate_content_ideas(
    request: Request,
    response: Response,
    payload: ContentIdeasIn,
) -> ContentIdeasOut:
    """Generate content ideas for a niche using Gemini. No auth required."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content idea generation is temporarily unavailable. The AI service is not configured.",
        )

    if idea_breaker.is_open(_IDEA_BREAKER_KEY):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content idea generation is temporarily unavailable. Try again in a moment.",
            headers={
                "Retry-After": str(max(1, int(idea_breaker.seconds_remaining(_IDEA_BREAKER_KEY))))
            },
        )

    niche = json.dumps(payload.niche, ensure_ascii=False)
    prompt = (
        f"You are an expert content strategist. Generate {payload.count} unique, "
        # ``json.dumps`` so the niche stays one quoted string: a quote or a
        # newline in it used to close the quotes and start instructions of its own.
        f"engaging content ideas for the niche: {niche}.\n\n"
        "For each idea, provide:\n"
        "- title: A compelling headline\n"
        "- hook: A one-sentence hook explaining why readers would care\n"
        "- content_type: One of: tutorial, how_to, comparison, announcement, "
        "feature_spotlight, product_spotlight\n\n"
        "Respond with ONLY a JSON array of objects. No markdown, no explanation.\n"
        "Example: [{\"title\": \"...\", \"hook\": \"...\", \"content_type\": \"tutorial\"}]"
    )

    try:
        resp = httpx.post(
            f"{settings.gemini_base_url}chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.gemini_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 2000,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        idea_breaker.record_success(_IDEA_BREAKER_KEY)
    except httpx.HTTPError as exc:
        if idea_breaker.record_failure(_IDEA_BREAKER_KEY):
            logger.warning("Gemini is failing; idea generation paused for 60s")
        logger.exception("Gemini API call failed for content ideas")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content idea generation is temporarily unavailable. Try again in a moment.",
        ) from exc

    try:
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise TypeError("message content is not text")
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        ideas = _parse_ideas(json.loads(text), payload.count)
        if not ideas:
            raise ValueError("no usable ideas in the response")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.exception(
            "Failed to parse Gemini response for content ideas; body=%s",
            resp.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not parse AI response. Please try again.",
        ) from exc

    return ContentIdeasOut(ideas=ideas, niche=payload.niche)
