"""Response models for the SEO automation endpoints (``/seo``)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
