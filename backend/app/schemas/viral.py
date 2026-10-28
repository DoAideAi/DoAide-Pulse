"""Schemas for viral / public-facing features."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.subscriber import SOURCE_MAX_LENGTH


class PublicArticleOut(BaseModel):
    """A published article visible to anyone with the link."""

    title: str
    slug: str
    body_markdown: str
    excerpt: str
    cover_image_url: str | None = None
    meta_description: str = ""
    tags: list[str] = []
    word_count: int = 0
    read_minutes: int = 1
    project_name: str | None = None
    published_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubscribeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    source: str = Field(default="embed", max_length=SOURCE_MAX_LENGTH)

    @field_validator("source", mode="before")
    @classmethod
    def _clip_source(cls, value: object) -> object:
        """A label too long for its column is clipped, not a reason to refuse.

        ``source`` is whatever the embedding page put in ``data-source``, which
        the widget forwards verbatim, so a long campaign string meant a 422 and
        every reader who signed up on that page was lost over an optional tag.
        """
        if not isinstance(value, str):
            return value
        value = " ".join(value.split())
        return value[:SOURCE_MAX_LENGTH] or "embed"


class SubscribeOut(BaseModel):
    ok: bool = True


class ContentIdeasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    niche: str = Field(min_length=2, max_length=200)
    count: int = Field(default=5, ge=1, le=10)


class ContentIdeasOut(BaseModel):
    ideas: list[ContentIdeaItem]
    niche: str


class ContentIdeaItem(BaseModel):
    title: str
    hook: str
    content_type: str


# Rebuild ContentIdeasOut now that ContentIdeaItem is defined.
ContentIdeasOut.model_rebuild()
