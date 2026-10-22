"""SEO health over time: daily snapshots and the sitemap submission run log.

The live SEO tables (:mod:`app.services.sitemaps`, :mod:`app.services.meta_audit`)
keep one overwritten row per site, which answers "where does each site stand
now". This module keeps the two records that question cannot: a daily total of
the estate's footing (for the charts), and one row per submission sweep (for
"did Monday's automated run happen, and did it work").

Both are written as a side effect of the sweeps that change the underlying
state, plus a nightly backstop task, so a day with no sweep still gets its
point on the chart.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.seo import MetaAudit, SeoHealthSnapshot, SitemapRun, SitemapStatus

#: Run-log rows kept; a year of weekly sweeps plus generous manual pressing.
RUNS_KEPT = 200


def record_snapshot(db: Session) -> SeoHealthSnapshot:
    """Upsert today's totals from what the live SEO tables already hold. Commits.

    Idempotent per day: a second sweep on the same date refreshes the same row,
    so the chart gets each day's *latest* state, never a duplicate point.
    """
    today = utcnow().date()
    sitemap_rows = db.scalars(select(SitemapStatus)).all()
    audit_rows = db.scalars(select(MetaAudit)).all()

    row = db.scalar(
        select(SeoHealthSnapshot).where(SeoHealthSnapshot.snapshot_date == today)
    )
    if row is None:
        row = SeoHealthSnapshot(snapshot_date=today)
        db.add(row)
    row.sites = len(sitemap_rows)
    row.sitemaps_submitted = sum(1 for r in sitemap_rows if r.submit_status == "submitted")
    row.sitemap_problems = sum(
        1 for r in sitemap_rows if r.fetch_error or r.submit_status == "error"
    )
    row.urls_in_sitemaps = sum(r.url_count or 0 for r in sitemap_rows)
    row.indexed_pages = sum(r.gsc_indexed or 0 for r in sitemap_rows)
    row.meta_issues = sum(a.issue_count for a in audit_rows if a.scanned_at)
    db.commit()
    return row


def history(db: Session, *, days: int = 90) -> list[dict]:
    """The last *days* of snapshots, oldest first — ready to chart."""
    since = utcnow().date() - timedelta(days=days)
    rows = db.scalars(
        select(SeoHealthSnapshot)
        .where(SeoHealthSnapshot.snapshot_date >= since)
        .order_by(SeoHealthSnapshot.snapshot_date)
    ).all()
    return [
        {
            "date": r.snapshot_date,
            "sites": r.sites,
            "sitemaps_submitted": r.sitemaps_submitted,
            "sitemap_problems": r.sitemap_problems,
            "urls_in_sitemaps": r.urls_in_sitemaps,
            "indexed_pages": r.indexed_pages,
            "meta_issues": r.meta_issues,
        }
        for r in rows
    ]


def record_run(db: Session, trigger: str, rows: Iterable[SitemapStatus]) -> SitemapRun:
    """Log one submission sweep over *rows*. Commits.

    Also prunes the log past :data:`RUNS_KEPT` — the page shows the recent
    tail, and a table that only ever grows is a disk-space bug on a timer.
    """
    rows = list(rows)
    problems = [
        {"site_key": r.site_key, "error": (r.fetch_error or r.submit_error or "")[:300]}
        for r in rows
        if r.fetch_error or r.submit_status == "error"
    ]
    run = SitemapRun(
        trigger=trigger,
        sites_checked=len(rows),
        sites_submitted=sum(1 for r in rows if r.submit_status == "submitted"),
        problems=problems,
        ran_at=utcnow(),
    )
    db.add(run)
    db.flush()
    stale = db.scalars(
        select(SitemapRun.id).order_by(SitemapRun.ran_at.desc()).offset(RUNS_KEPT)
    ).all()
    if stale:
        for row_id in stale:
            db.delete(db.get(SitemapRun, row_id))
    db.commit()
    return run


def runs(db: Session, *, limit: int = 20) -> list[dict]:
    """The most recent submission sweeps, newest first."""
    rows = db.scalars(
        select(SitemapRun).order_by(SitemapRun.ran_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "trigger": r.trigger,
            "sites_checked": r.sites_checked,
            "sites_submitted": r.sites_submitted,
            "problems": r.problems,
            "ran_at": r.ran_at,
        }
        for r in rows
    ]
