"""Everything an account has written, as one JSON document (C104 M9).

``DELETE /auth/me`` erases an account; there was no way to take the work out
first. This is that way: the profile, the projects, every piece with its body,
its translations and where it went live, the templates and the idea backlog — what a person
would need to carry their writing somewhere else.

Deliberately absent: anything that is a credential or a capability. Platform
connections, API keys, webhook and trigger secrets, the account's own LLM key,
the password hash. An export is a file that gets emailed and left in Downloads,
and none of those belongs in one.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.content import Content, ContentIdea
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.template import ContentTemplate
from app.models.user import User

#: Bumped when the shape changes, so a reader can tell two exports apart.
#: 2 — each piece carries its translations and its ``scheduled_for`` (M2).
FORMAT_VERSION = 2


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _enum(value: Any) -> Any:
    return getattr(value, "value", value)


def _project(p: Project) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "repo_url": p.repo_url,
        "live_url": p.live_url,
        "tech_stack": p.tech_stack,
        "target_audience": p.target_audience,
        "keywords": p.keywords,
        "tone": _enum(p.tone),
        "autopilot_mode": _enum(p.autopilot_mode),
        "autopilot_platforms": p.autopilot_platforms,
        "created_at": _iso(p.created_at),
    }


def _piece(c: Content) -> dict[str, Any]:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "content_type": _enum(c.content_type),
        "status": _enum(c.status),
        "title": c.title,
        "slug": c.slug,
        "body_markdown": c.body_markdown,
        "excerpt": c.excerpt,
        "meta_description": c.meta_description,
        "keywords": c.keywords,
        "tags": c.tags,
        "focus_keyword": c.focus_keyword,
        "canonical_url": c.canonical_url,
        "cover_image_url": c.cover_image_url,
        "marketing_images": c.marketing_images,
        "created_at": _iso(c.created_at),
        "scheduled_for": _iso(c.scheduled_for),
        "published_at": _iso(c.published_at),
        # The piece in every other language it was written in. Left out
        # until version 2, so an account that had translated its work
        # and then erased itself took only the originals: the export is
        # the one way out, and the translations went with the account.
        "translations": [
            {
                "language": t.language,
                "status": _enum(t.status),
                "title": t.title,
                "body_markdown": t.body_markdown,
                "excerpt": t.excerpt,
                "meta_description": t.meta_description,
                "stale": t.is_stale(c),
                "translated_at": _iso(t.translated_at),
            }
            for t in sorted(c.translations, key=lambda t: t.language)
        ],
        "publications": [
            {
                "platform": _enum(p.platform),
                "status": _enum(p.status),
                "external_url": p.external_url,
                "published_at": _iso(p.published_at),
            }
            for p in c.publications
        ],
    }


def _template(t: ContentTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "mode": _enum(t.mode),
        "content_type": _enum(t.content_type),
        "title_template": t.title_template,
        "body_template": t.body_template,
        "variables": t.variables,
    }


def _idea(i: ContentIdea) -> dict[str, Any]:
    return {
        "id": i.id,
        "project_id": i.project_id,
        "content_type": _enum(i.content_type),
        "headline": i.headline,
        "rationale": i.rationale,
        "planned_date": _iso(i.planned_date),
    }


def _everything_but_the_pieces(db: Session, user: User) -> tuple[dict[str, Any], list[int]]:
    projects = list(
        db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.id))
    )
    project_ids = [p.id for p in projects]
    ideas = db.scalars(
        select(ContentIdea)
        .where(ContentIdea.project_id.in_(project_ids or [0]))
        .order_by(ContentIdea.id)
    )
    templates = db.scalars(
        select(ContentTemplate)
        .where(ContentTemplate.user_id == user.id)
        .order_by(ContentTemplate.id)
    )
    head = {
        "format_version": FORMAT_VERSION,
        "exported_at": utcnow().isoformat(),
        "account": {
            "email": user.email,
            "full_name": user.full_name,
            "created_at": _iso(user.created_at),
        },
        "projects": [_project(p) for p in projects],
        "templates": [_template(t) for t in templates],
        "ideas": [_idea(i) for i in ideas],
    }
    return head, project_ids


#: Pieces loaded per query while streaming. Each carries a body of up to
#: 200,000 characters plus its translations, so this is what bounds memory.
STREAM_BATCH = 100


def _pieces(db: Session, project_ids: list[int]) -> Iterator[Content]:
    """Every piece, in id order, one batch in memory at a time."""
    after = 0
    while True:
        batch = list(
            db.scalars(
                select(Content)
                .where(Content.project_id.in_(project_ids or [0]), Content.id > after)
                .options(
                    selectinload(Content.publications), selectinload(Content.translations)
                )
                .order_by(Content.id)
                .limit(STREAM_BATCH)
            )
        )
        if not batch:
            return
        yield from batch
        after = batch[-1].id
        # Out of the identity map, or the session keeps every batch alive and
        # the stream holds the whole account in memory after all.
        for piece in batch:
            for child in (*piece.publications, *piece.translations):
                db.expunge(child)
            db.expunge(piece)


def build(db: Session, user: User) -> dict[str, Any]:
    """The whole account as one dict. :func:`stream` is what the route serves."""
    head, project_ids = _everything_but_the_pieces(db, user)
    return {**head, "content": [_piece(c) for c in _pieces(db, project_ids)]}


def stream(db: Session, user: User) -> Iterator[bytes]:
    """The same document as :func:`build`, written out a piece at a time.

    ``build`` held every body the account had written — up to 200,000
    characters each, plus every translation — as Python objects, then again
    as the validated response model, then again as the serialised JSON: three
    or four copies of the whole account at once, in an API worker every other
    request shares. An autopilot account a year old has thousands of pieces.
    This keeps one batch of :data:`STREAM_BATCH` in memory and the rest on the
    wire. The small sections go first; ``content`` is the last key.
    """
    head, project_ids = _everything_but_the_pieces(db, user)
    opening = json.dumps(head, ensure_ascii=False)
    yield (opening[:-1] + ', "content": [').encode()
    first = True
    for piece in _pieces(db, project_ids):
        yield (("" if first else ", ") + json.dumps(_piece(piece), ensure_ascii=False)).encode()
        first = False
    yield b"]}"


__all__ = ["FORMAT_VERSION", "STREAM_BATCH", "build", "stream"]
