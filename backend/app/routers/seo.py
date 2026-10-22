"""SEO automation across every DoAide site (``/seo``).

Read and run by a product admin — the same gate as the cross-product activity
dashboard, because these endpoints report on, and act for, the whole estate
rather than one Pulse user's content.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.routers.product_activity import require_product_admin
from app.schemas.errors import AUTHENTICATED, errors
from app.schemas.seo import SitemapsOut
from app.services import search_console, seo_sites, sitemaps

router = APIRouter(prefix="/seo", tags=["seo"])


def _sitemaps_payload(db: Session) -> dict:
    gsc = search_console.get_client()
    return {
        "gsc_configured": gsc.configured,
        "gsc_account": gsc.client_email,
        "sites": sitemaps.status(db),
    }


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
    sitemaps.check(db, targets)
    return _sitemaps_payload(db)
