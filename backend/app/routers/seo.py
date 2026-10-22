"""SEO automation across every DoAide site (``/seo``).

Read and run by a product admin — the same gate as the cross-product activity
dashboard, because these endpoints report on, and act for, the whole estate
rather than one Pulse user's content.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.publication import Platform
from app.models.user import User
from app.routers.product_activity import require_product_admin
from app.schemas.content import SlotOut
from app.schemas.errors import AUTHENTICATED, errors
from app.schemas.seo import LinkSuggestionsIn, LinkSuggestionsOut, SeoPostOut, SitemapsOut
from app.services import scheduling, search_console, seo_posts, seo_sites, sitemaps

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
