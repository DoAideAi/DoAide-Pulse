"""SEO housekeeping: keep every DoAide sitemap submitted to Google."""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services import sitemaps
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
        failed = [r.site_key for r in rows if r.fetch_error or r.submit_status == "error"]
        if failed:
            logger.warning("sitemaps: problems on %s", ", ".join(failed))
        return {"checked": len(rows), "problems": failed}
    finally:
        db.close()
