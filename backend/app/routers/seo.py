"""SEO automation across every DoAide site (``/seo``).

Read and run by a product admin — the same gate as the cross-product activity
dashboard, because these endpoints report on, and act for, the whole estate
rather than one Pulse user's content.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.publication import Platform
from app.models.user import User
from app.routers.product_activity import require_product_admin
from app.schemas.content import SlotOut
from app.schemas.errors import AUTHENTICATED, errors
from app.schemas.seo import (
    AuditQueuedOut,
    LinkSuggestionsIn,
    LinkSuggestionsOut,
    MetaAuditOut,
    SeoHealthHistoryOut,
    SeoHealthOut,
    SeoPostOut,
    SeoTrafficOut,
    SitemapRunsOut,
    SitemapsOut,
)
from app.services import (
    meta_audit,
    scheduling,
    search_console,
    seo_health,
    seo_history,
    seo_posts,
    seo_sites,
    seo_traffic,
    sitemaps,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seo", tags=["seo"])


def _sitemaps_payload(db: Session) -> dict:
    gsc = search_console.get_client()
    return {
        "gsc_configured": gsc.configured,
        "gsc_account": gsc.client_email,
        "sites": sitemaps.status(db),
    }


@router.get(
    "/health",
    response_model=SeoHealthOut,
    summary="Sitemaps, indexed pages, recent posts and the content calendar",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def health(
    tz: str = Query(default="UTC", max_length=64, description="IANA zone for calendar days."),
    db: Session = Depends(get_db),
    user: User = Depends(require_product_admin),
) -> dict:
    """Reads only what Pulse already stored — no fetch to Google or the sites —
    so it is cheap enough to open on every visit."""
    return seo_health.health(db, user.id, tz=tz)


@router.get(
    "/health/history",
    response_model=SeoHealthHistoryOut,
    summary="Daily SEO health totals for the chart",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def health_history(
    days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    """One point per day: sitemap URLs, indexed pages, problems and meta
    issues across the estate. Written nightly and by every sweep, read here."""
    return {"days": days, "points": seo_history.history(db, days=days)}


@router.get(
    "/sitemaps",
    response_model=SitemapsOut,
    summary="Sitemap state for every DoAide site",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def list_sitemaps(
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    return _sitemaps_payload(db)


@router.post(
    "/sitemaps/submit",
    response_model=SitemapsOut,
    summary="Fetch and submit sitemaps to Google Search Console",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
)
def submit_sitemaps(
    site: str | None = Query(default=None, description="One site key; omit for all."),
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    """Synchronous: fourteen small sitemaps in parallel is seconds, and the
    person who pressed the button wants the answer, not a job id."""
    if site is None:
        targets = seo_sites.SITES
    elif site in seo_sites.BY_KEY:
        targets = (seo_sites.BY_KEY[site],)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown site.")
    rows = sitemaps.check(db, targets)
    seo_history.record_run(db, "manual", rows)
    seo_history.record_snapshot(db)
    return _sitemaps_payload(db)


@router.get(
    "/sitemaps/runs",
    response_model=SitemapRunsOut,
    summary="Recent sitemap submission sweeps, scheduled and manual",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def sitemap_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    """The status page for the automated weekly submission: when each sweep
    ran, what triggered it, and which sites had problems."""
    return {"runs": seo_history.runs(db, limit=limit)}


# ---- meta-tag audit ----


def _audit_payload(db: Session) -> dict:
    return {"issue_labels": meta_audit.ISSUES, "sites": meta_audit.summary(db)}


@router.get(
    "/audit",
    response_model=MetaAuditOut,
    summary="The latest meta-tag audit of every DoAide site",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def get_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    return _audit_payload(db)


@router.post(
    "/audit",
    response_model=MetaAuditOut | AuditQueuedOut,
    summary="Audit one site now, or queue every site",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
)
def run_audit(
    response: Response,
    background: BackgroundTasks,
    site: str | None = Query(default=None, description="One site key; omit to queue all."),
    db: Session = Depends(get_db),
    _: User = Depends(require_product_admin),
) -> dict:
    """One site runs in the request — up to ``seo_audit_max_pages`` fetches,
    four at a time. All fourteen is minutes of fetching, so it goes to the
    worker and the answer is 202; the page re-reads ``GET /seo/audit``."""
    if site is None:
        from app.tasks import seo_tasks

        # Same shape as the content router's dispatch: the worker if there is
        # one, otherwise after the response on this process, so the button
        # still does what it says when Redis is down.
        queued = False
        if settings.celery_enabled:
            try:
                seo_tasks.audit_meta_tags.delay()
                queued = True
            except Exception as exc:
                logger.warning("meta audit dispatch failed, running inline: %s", exc)
        if not queued:
            background.add_task(seo_tasks.audit_meta_tags)
        response.status_code = status.HTTP_202_ACCEPTED
        return {"queued": True}
    if site not in seo_sites.BY_KEY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown site.")
    meta_audit.run(db, [seo_sites.BY_KEY[site]])
    return _audit_payload(db)


# ---- traffic (Umami) ----


@router.get(
    "/traffic",
    response_model=SeoTrafficOut,
    summary="Which pages and referrers bring visitors to each DoAide site",
    responses=errors(*AUTHENTICATED, status.HTTP_403_FORBIDDEN),
)
def traffic(
    days: int = Query(default=30, ge=1, le=90),
    refresh: bool = Query(default=False, description="Skip the Umami cache."),
    db: Session = Depends(get_db),
    user: User = Depends(require_product_admin),
) -> dict:
    return seo_traffic.traffic(db, user.id, days=days, force=refresh)


# ---- SEO posts ----
#
# These act on the caller's own content, so they take a signed-in user rather
# than a product admin: writing a post needs no view of the whole estate.


@router.get(
    "/posts",
    response_model=list[SeoPostOut],
    summary="Your SEO posts: scheduled first, then the rest",
    responses=errors(*AUTHENTICATED),
)
def list_seo_posts(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return seo_posts.queue(db, user.id, limit=limit)


@router.post(
    "/link-suggestions",
    response_model=LinkSuggestionsOut,
    summary="Internal links for a draft: your posts and DoAide product pages",
    responses=errors(*AUTHENTICATED),
)
def link_suggestions(
    payload: LinkSuggestionsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Deterministic — keyword overlap and topic matching, no model call — so
    the editor can ask on every pause in typing."""
    return {
        "posts": seo_posts.post_links(
            db,
            user.id,
            keywords=payload.keywords,
            focus_keyword=payload.focus_keyword,
            exclude_content_id=payload.content_id,
        ),
        "products": seo_posts.product_links(
            title=payload.title,
            body_markdown=payload.body_markdown,
            keywords=[*payload.keywords, payload.focus_keyword],
        ),
    }


@router.get(
    "/optimal-slots",
    response_model=list[SlotOut],
    summary="When Pulse would publish a new post, per platform",
    responses=errors(*AUTHENTICATED, status.HTTP_400_BAD_REQUEST),
)
def optimal_slots(
    platforms: list[Platform] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SlotOut]:
    """The same slots ``POST /content/{id}/schedule`` with ``optimize`` would
    pick, asked before the piece exists so the editor can show them."""
    wanted = list(platforms or []) or [Platform(p) for p in user.connected_platforms]
    if not wanted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name the platforms — none is connected yet.",
        )
    return [SlotOut(**slot.as_dict()) for slot in scheduling.optimal_slots(db, user.id, wanted)]
