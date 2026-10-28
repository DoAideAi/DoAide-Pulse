"""Everything an account has written, as one JSON document (C104 M9).

``DELETE /auth/me`` erases an account; there was no way to take the work out
first. This is that way: the profile, the projects, every piece with its body
and where it went live, the templates and the idea backlog — what a person
would need to carry their writing somewhere else.

Deliberately absent: anything that is a credential or a capability. Platform
connections, API keys, webhook and trigger secrets, the account's own LLM key,
the password hash. An export is a file that gets emailed and left in Downloads,
and none of those belongs in one.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.content import Content, ContentIdea
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.template import ContentTemplate
from app.models.user import User

#: Bumped when the shape changes, so a reader can tell two exports apart.
FORMAT_VERSION = 1


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _enum(value: Any) -> Any:
    return getattr(value, "value", value)


def build(db: Session, user: User) -> dict[str, Any]:
    """The whole account, ready to serialise."""
    projects = list(
        db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.id))
    )
    project_ids = [p.id for p in projects]
    content = list(
        db.scalars(
            select(Content)
            .where(Content.project_id.in_(project_ids or [0]))
            .options(selectinload(Content.publications))
            .order_by(Content.id)
        )
    )
    ideas = list(
        db.scalars(
            select(ContentIdea)
            .where(ContentIdea.project_id.in_(project_ids or [0]))
            .order_by(ContentIdea.id)
        )
    )
    templates = list(
        db.scalars(
            select(ContentTemplate)
            .where(ContentTemplate.user_id == user.id)
            .order_by(ContentTemplate.id)
        )
    )

    return {
        "format_version": FORMAT_VERSION,
        "exported_at": utcnow().isoformat(),
        "account": {
            "email": user.email,
            "full_name": user.full_name,
            "created_at": _iso(user.created_at),
        },
        "projects": [
            {
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
            for p in projects
        ],
        "content": [
            {
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
                "published_at": _iso(c.published_at),
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
            for c in content
        ],
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "mode": _enum(t.mode),
                "content_type": _enum(t.content_type),
                "title_template": t.title_template,
                "body_template": t.body_template,
                "variables": t.variables,
            }
            for t in templates
        ],
        "ideas": [
            {
                "id": i.id,
                "project_id": i.project_id,
                "content_type": _enum(i.content_type),
                "headline": i.headline,
                "rationale": i.rationale,
                "planned_date": _iso(i.planned_date),
            }
            for i in ideas
        ],
    }


__all__ = ["FORMAT_VERSION", "build"]
