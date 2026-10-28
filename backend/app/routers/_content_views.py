"""How a ``Content`` row is shaped for the API.

Shared by every router that answers with a piece: ``/content`` itself, and
``/templates/{id}/use``, which writes one. They lived in the content router as
private helpers, and the templates router imported them from there — one
router reaching into another's privates, with a function-level import to dodge
the cycle that would otherwise follow. Here they are a module of their own,
like :mod:`app.routers._patch`.
"""
from __future__ import annotations

from app.models.content import Content
from app.schemas.content import (
    ContentDetail,
    ContentOut,
    PublicationOut,
    QualityOut,
    SeoIssueOut,
)
from app.services import formats, quality, seo


def to_out(content: Content) -> ContentOut:
    """A listing row. Reads no article text — see the ``defer`` on its callers.

    ``word_count`` and ``read_minutes`` both come off the stored count now, so
    the only field here that would touch ``body_markdown`` is one nobody added.
    The paged callers below defer that column so a listing of 500 pieces stops
    shipping 500 article bodies to render 500 word counts; ``to_detail``, which
    genuinely wants the text, does not defer it.
    """
    return ContentOut(
        **{
            key: getattr(content, key)
            for key in (
                "id", "project_id", "content_type", "status", "title", "slug",
                "excerpt", "meta_description", "keywords", "tags", "canonical_url",
                "cover_image_url", "marketing_images", "focus_keyword", "version",
                "confidence", "generated_by_provider", "generated_by_model",
                "source", "scheduled_for", "published_at", "created_at", "updated_at",
            )
        },
        project_name=content.project.name if content.project else None,
        word_count=content.word_count,
        read_minutes=content.read_minutes,
        content_format=formats.format_of(content.content_type).value,
        publications=[PublicationOut.model_validate(p) for p in content.publications],
    )


def to_detail(content: Content) -> ContentDetail:
    """One piece in full: the listing row plus its text and what the checks say."""
    issues = seo.audit(
        title=content.title,
        body_markdown=content.body_markdown,
        meta_description=content.meta_description,
        keywords=list(content.keywords or []),
        cover_image_url=content.cover_image_url,
        focus_keyword=getattr(content, "focus_keyword", "") or "",
        slug=content.slug,
    )
    qr = quality.report_for(content)
    out = to_out(content)
    out.seo_score = qr.seo_score
    return ContentDetail(
        **out.model_dump(),
        body_markdown=content.body_markdown,
        seo_issues=[
            SeoIssueOut(level=i.level, field=i.field, message=i.message) for i in issues
        ],
        format_issues=formats.problems(content.body_markdown, content.content_type),
        quality=QualityOut(**qr.as_dict()),
    )


__all__ = ["to_detail", "to_out"]
