"""Sitemaps for every DoAide site: fetched, counted, and submitted to Google.

Two halves, deliberately independent:

* **Fetch** — Pulse downloads each site's sitemap itself and counts its URLs.
  Needs no Google credentials, so the dashboard can say "comply.doaide.com's
  sitemap is a 404" before anyone has set up a service account.
* **Submit** — the sitemap is (re)submitted to Search Console and Google's own
  counts are read back. Skipped, and recorded as ``unconfigured``, without a
  service account.

A sitemap that fails to fetch is still submitted: Google's verdict on it is
the more useful one, and a fetch can fail on our side for reasons Google's
crawler does not share.

Parsing is a regex over ``<loc>``, not an XML parser. A sitemap is the one XML
document whose only interesting content is one element, and a regex cannot be
made to expand entities, which ``xml.etree`` on untrusted input can.
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.mixins import utcnow
from app.models.seo import SitemapStatus
from app.services import search_console, seo_sites
from app.services.search_console import SearchConsoleClient, SearchConsoleError
from app.services.seo_sites import SITES, Site

logger = logging.getLogger(__name__)

#: A sitemap may hold 50,000 URLs and be 50 MB uncompressed; DoAide's are a
#: few hundred. Anything past this is read no further.
MAX_SITEMAP_BYTES = 5 * 1024 * 1024
#: Child sitemaps followed from a sitemap index.
MAX_CHILD_SITEMAPS = 10
USER_AGENT = "PulseSEO/1.0 (+https://pulse.doaide.com)"

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_INDEX = re.compile(r"<sitemapindex\b", re.IGNORECASE)


class FetchError(Exception):
    """The page could not be fetched, or was not on the site's own host."""


def http_client(timeout: float, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    )


def fetch(client: httpx.Client, site: Site, url: str, *, max_bytes: int) -> tuple[str, str]:
    """GET *url* and return ``(final_url, text)``, at most *max_bytes* of it.

    Refuses a URL — or a redirect — off *site*'s own host. Streams, so a page
    that turns out to be enormous costs *max_bytes*, not its size.
    """
    if not seo_sites.owns(site, url):
        raise FetchError(f"{url} is not on {site.domain}")
    try:
        with client.stream("GET", url) as resp:
            final = str(resp.url)
            if not seo_sites.owns(site, final):
                raise FetchError(f"{url} redirected off {site.domain}")
            if resp.status_code != 200:
                raise FetchError(f"{url} answered {resp.status_code}")
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= max_bytes:
                    break
            encoding = resp.encoding or "utf-8"
    except httpx.HTTPError as exc:
        raise FetchError(f"{url} unreachable: {type(exc).__name__}") from exc
    return final, b"".join(chunks)[:max_bytes].decode(encoding, errors="replace")


def parse_locs(xml: str) -> tuple[bool, list[str]]:
    """``(is_index, locations)`` from a sitemap or sitemap index."""
    locs = [html.unescape(m).strip() for m in _LOC.findall(xml)]
    return bool(_INDEX.search(xml)), [u for u in locs if u]


def sitemap_urls(client: httpx.Client, site: Site) -> list[str]:
    """Every page URL in *site*'s sitemap, following one level of index."""
    _, text = fetch(client, site, site.sitemap_url, max_bytes=MAX_SITEMAP_BYTES)
    is_index, locs = parse_locs(text)
    if not is_index:
        return [u for u in locs if seo_sites.owns(site, u)]
    pages: list[str] = []
    for child in [u for u in locs if seo_sites.owns(site, u)][:MAX_CHILD_SITEMAPS]:
        try:
            _, child_text = fetch(client, site, child, max_bytes=MAX_SITEMAP_BYTES)
        except FetchError as exc:
            logger.info("sitemap: %s child %s skipped: %s", site.key, child, exc)
            continue
        pages.extend(u for u in parse_locs(child_text)[1] if seo_sites.owns(site, u))
    return pages


def _row(db: Session, site: Site) -> SitemapStatus:
    row = db.scalar(select(SitemapStatus).where(SitemapStatus.site_key == site.key))
    if row is None:
        row = SitemapStatus(site_key=site.key, sitemap_url=site.sitemap_url)
        db.add(row)
    row.sitemap_url = site.sitemap_url
    return row


def _check_one(
    site: Site,
    gsc: SearchConsoleClient,
    *,
    submit: bool,
    transport: httpx.BaseTransport | None,
) -> dict:
    """Everything that needs the network for one site, with no session held."""
    out: dict = {"url_count": None, "fetch_error": None}
    with http_client(settings.seo_audit_timeout_seconds, transport) as client:
        try:
            out["url_count"] = len(sitemap_urls(client, site))
        except FetchError as exc:
            out["fetch_error"] = str(exc)

    if not gsc.configured:
        out["submit_status"] = "unconfigured"
        return out
    prop = search_console.property_for(site.domain)
    try:
        if submit:
            gsc.submit(prop, site.sitemap_url)
            out["submitted"] = True
        out["gsc"] = gsc.sitemap(prop, site.sitemap_url)
        out["submit_status"] = "submitted"
    except SearchConsoleError as exc:
        out["submit_status"] = "error"
        out["submit_error"] = str(exc)
    return out


def check(
    db: Session,
    sites: Iterable[Site] = SITES,
    *,
    submit: bool = True,
    gsc: SearchConsoleClient | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[SitemapStatus]:
    """Fetch, (re)submit and read back each of *sites*. Commits.

    The network work runs in parallel and outside any transaction; the rows
    are written afterwards in one commit.
    """
    gsc = gsc or search_console.get_client()
    sites = list(sites)
    with ThreadPoolExecutor(max_workers=min(6, len(sites) or 1)) as pool:
        results = list(
            pool.map(lambda s: _check_one(s, gsc, submit=submit, transport=transport), sites)
        )

    now = utcnow()
    rows = []
    for site, result in zip(sites, results, strict=True):
        row = _row(db, site)
        row.url_count = result["url_count"]
        row.fetch_error = result["fetch_error"]
        row.submit_status = result["submit_status"]
        row.submit_error = result.get("submit_error")
        if result.get("submitted"):
            row.submitted_at = now
        if "gsc" in result:
            g = result["gsc"]
            row.gsc_submitted = g["submitted"]
            row.gsc_indexed = g["indexed"]
            row.gsc_errors = g["errors"]
            row.gsc_warnings = g["warnings"]
            row.gsc_last_downloaded = g["last_downloaded"]
        row.checked_at = now
        rows.append(row)
    db.commit()
    return rows


def status(db: Session) -> list[dict]:
    """Every site in the catalog with its latest sitemap state, checked or not."""
    rows = {r.site_key: r for r in db.scalars(select(SitemapStatus)).all()}
    out = []
    for site in SITES:
        r = rows.get(site.key)
        out.append(
            {
                "key": site.key,
                "name": site.name,
                "domain": site.domain,
                "url": site.url,
                "sitemap_url": site.sitemap_url,
                "checked": r is not None and r.checked_at is not None,
                "url_count": r.url_count if r else None,
                "fetch_error": r.fetch_error if r else None,
                "submit_status": r.submit_status if r else "pending",
                "submit_error": r.submit_error if r else None,
                "gsc_submitted": r.gsc_submitted if r else None,
                "gsc_indexed": r.gsc_indexed if r else None,
                "gsc_errors": r.gsc_errors if r else None,
                "gsc_warnings": r.gsc_warnings if r else None,
                "gsc_last_downloaded": r.gsc_last_downloaded if r else None,
                "submitted_at": r.submitted_at if r else None,
                "checked_at": r.checked_at if r else None,
            }
        )
    return out
