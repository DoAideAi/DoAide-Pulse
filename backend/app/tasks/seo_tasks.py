"""SEO housekeeping: keep every DoAide sitemap submitted to Google."""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services import meta_audit, seo_history, sitemaps
from app.tasks.celery_app import task

logger = logging.getLogger(__name__)


@task(
    name="app.tasks.seo_tasks.submit_sitemaps",
    soft_time_limit=300,
    time_limit=360,
)
def submit_sitemaps() -> dict:
    """Fetch, resubmit and read back every site's sitemap.

    Resubmitting an unchanged sitemap is harmless and is what nudges Google to
    re-read it after a product ships new pages, which is the whole point of
    doing it on a schedule rather than once.
    """
    db = SessionLocal()
    try:
        rows = sitemaps.check(db)
        seo_history.record_run(db, "scheduled", rows)
        seo_history.record_snapshot(db)
        failed = [r.site_key for r in rows if r.fetch_error or r.submit_status == "error"]
        if failed:
            logger.warning("sitemaps: problems on %s", ", ".join(failed))
        logger.info("sitemaps: %d checked, %d with problems", len(rows), len(failed))
        return {"checked": len(rows), "problems": failed}
    finally:
        db.close()


@task(
    name="app.tasks.seo_tasks.audit_meta_tags",
    soft_time_limit=900,
    time_limit=960,
)
def audit_meta_tags() -> dict:
    """Audit every site's meta tags. Sequential by site, a few pages at a time
    within one, so a sweep is a trickle of requests rather than a burst."""
    db = SessionLocal()
    try:
        rows = meta_audit.run(db)
        seo_history.record_snapshot(db)
        issues = sum(r.issue_count for r in rows)
        # A site whose sitemap could not be read was stored with its error and
        # nothing else said so: the audit then covers one page and reports it
        # clean, which reads as good news. Named here like the sitemap sweep's.
        failed = [r.site_key for r in rows if r.error]
        if failed:
            logger.warning("meta audit: problems on %s", ", ".join(failed))
        logger.info(
            "meta audit: %d site(s), %d issue(s), %d with problems",
            len(rows), issues, len(failed),
        )
        return {"audited": len(rows), "issues": issues}
    finally:
        db.close()


@task(
    name="app.tasks.seo_tasks.record_seo_snapshot",
    soft_time_limit=60,
    time_limit=90,
)
def record_seo_snapshot() -> dict:
    """The nightly backstop for the health-over-time chart.

    The sweeps write a snapshot when they run, but they run weekly; without
    this, the chart would have one point a week and flat interpolation would
    pass for data. Reads only what Pulse already stored — no network.
    """
    db = SessionLocal()
    try:
        row = seo_history.record_snapshot(db)
        return {"date": row.snapshot_date.isoformat(), "urls": row.urls_in_sitemaps}
    finally:
        db.close()
