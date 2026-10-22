"""Response models for the SEO automation endpoints (``/seo``)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.content import BODY_MARKDOWN_MAX_LENGTH, TITLE_MAX_LENGTH
from app.schemas.content import InternalLinkSuggestionOut
from app.schemas.limits import BoundedId, Keyword


class SitemapOut(BaseModel):
    key: str
    name: str
    domain: str
    url: str
    sitemap_url: str
    #: False until the first check has run for this site.
    checked: bool
    url_count: int | None = None
    fetch_error: str | None = None
    #: ``pending`` (never checked), ``submitted``, ``error`` or ``unconfigured``.
    submit_status: str
    submit_error: str | None = None
    gsc_submitted: int | None = None
    gsc_indexed: int | None = None
    gsc_errors: int | None = None
    gsc_warnings: int | None = None
    gsc_last_downloaded: str | None = None
    submitted_at: datetime | None = None
    checked_at: datetime | None = None


class SitemapsOut(BaseModel):
    #: Whether a Search Console service account is configured.
    gsc_configured: bool
    #: The service account's email — what to add as an Owner in Search Console.
    gsc_account: str | None = None
    sites: list[SitemapOut]


class LinkSuggestionsIn(BaseModel):
    """A draft, saved or not — the editor asks while the author is typing."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=TITLE_MAX_LENGTH)
    body_markdown: str = Field(default="", max_length=BODY_MARKDOWN_MAX_LENGTH)
    keywords: list[Keyword] = Field(default=[], max_length=30)
    focus_keyword: str = Field(default="", max_length=100)
    #: The piece being edited, so it is not suggested as a link to itself.
    content_id: BoundedId | None = None


class ProductLinkOut(BaseModel):
    """A DoAide product site the draft is about and does not yet link to."""

    site_key: str
    name: str
    url: str
    #: The matched topic, as a ready-made anchor text.
    anchor: str
    matched_topics: list[str]
    score: int


class LinkSuggestionsOut(BaseModel):
    posts: list[InternalLinkSuggestionOut]
    products: list[ProductLinkOut]


class SeoPostOut(BaseModel):
    id: int
    title: str
    slug: str
    status: str
    project_name: str | None = None
    focus_keyword: str = ""
    keywords: list[str] = []
    meta_description_length: int = 0
    word_count: int = 0
    scheduled_for: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime


class HealthSiteOut(BaseModel):
    key: str
    name: str
    domain: str
    url: str
    checked: bool
    url_count: int | None = None
    fetch_error: str | None = None
    submit_status: str
    submit_error: str | None = None
    gsc_submitted: int | None = None
    gsc_indexed: int | None = None
    gsc_errors: int | None = None
    checked_at: datetime | None = None
    #: SEO posts published in the last 30 days by a project living on this site.
    recent_posts: int
    scheduled_posts: int


class HealthTotalsOut(BaseModel):
    sites: int
    sitemaps_submitted: int
    sitemap_problems: int
    urls_in_sitemaps: int
    indexed_pages: int
    posts_published_30d: int
    posts_scheduled: int


class RecentSeoPostOut(SeoPostOut):
    site_key: str | None = None


class CalendarEntryOut(BaseModel):
    id: int
    title: str
    status: str
    when: datetime


class CalendarDayOut(BaseModel):
    date: date
    posts: list[CalendarEntryOut]


class SeoHealthOut(BaseModel):
    generated_at: datetime
    totals: HealthTotalsOut
    sites: list[HealthSiteOut]
    recent_posts: list[RecentSeoPostOut]
    calendar: list[CalendarDayOut]
