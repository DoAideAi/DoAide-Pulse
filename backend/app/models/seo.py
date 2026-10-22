"""What Pulse last learned about each DoAide site's sitemap and meta tags.

One row per site in :mod:`app.services.seo_sites`, keyed by its ``site_key``
and overwritten on every check — the dashboard asks "where does each site stand
now", not "how did it get here". Not owned by a Pulse user, for the same reason
:class:`app.models.product_event.ProductEvent` is not: the rows describe the
estate, and only a product admin reads them.
"""
from __future__ import annotations

# Imported at runtime: SQLAlchemy resolves Mapped[...] at class-definition time.
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

SITE_KEY_MAX_LENGTH = 40


class SitemapStatus(Base, TimestampMixin):
    __tablename__ = "seo_sitemaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_key: Mapped[str] = mapped_column(
        String(SITE_KEY_MAX_LENGTH), unique=True, nullable=False
    )
    sitemap_url: Mapped[str] = mapped_column(String(500), nullable=False)
    #: How many <loc> entries the sitemap had when Pulse last fetched it
    #: itself. Null when the fetch failed.
    url_count: Mapped[int | None] = mapped_column(Integer)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    #: ``submitted``, ``error`` or ``unconfigured`` (no service account).
    submit_status: Mapped[str] = mapped_column(String(20), default="unconfigured", nullable=False)
    submit_error: Mapped[str | None] = mapped_column(Text)
    #: As Search Console reports them. ``indexed`` is often 0 because Google
    #: stopped filling it in, not because nothing is indexed.
    gsc_submitted: Mapped[int | None] = mapped_column(Integer)
    gsc_indexed: Mapped[int | None] = mapped_column(Integer)
    gsc_errors: Mapped[int | None] = mapped_column(Integer)
    gsc_warnings: Mapped[int | None] = mapped_column(Integer)
    gsc_last_downloaded: Mapped[str | None] = mapped_column(String(40))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SeoHealthSnapshot(Base, TimestampMixin):
    """One row per day: the estate's search footing, summed across sites.

    Written once a day (and refreshed by every sitemap or audit sweep that
    lands on the same day), so the dashboard can draw "how did it get here"
    next to the live table that answers "where does it stand now".
    """

    __tablename__ = "seo_health_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    sites: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sitemaps_submitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sitemap_problems: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    urls_in_sitemaps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta_issues: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SitemapRun(Base, TimestampMixin):
    """One row per sitemap submission sweep, scheduled or button-pressed.

    The run log answers "did Monday's automated submission actually happen,
    and did it work" — something the per-site snapshot cannot, because a later
    manual submit of one site overwrites the evidence.
    """

    __tablename__ = "seo_sitemap_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: ``scheduled`` (the weekly beat job) or ``manual`` (the dashboard button).
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    sites_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_submitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Site keys whose fetch or submission failed, with the first error line.
    problems: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetaAudit(Base, TimestampMixin):
    __tablename__ = "seo_meta_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_key: Mapped[str] = mapped_column(
        String(SITE_KEY_MAX_LENGTH), unique=True, nullable=False
    )
    pages_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: The full report: per-page findings and the site-wide duplicates.
    report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
