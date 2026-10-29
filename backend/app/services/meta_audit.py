"""The meta-tag auditor: what each DoAide page tells search engines and link cards.

For each site, the homepage plus the first ``seo_audit_max_pages`` URLs of its
sitemap are fetched and their ``<head>`` read for the tags that decide how a
page appears in Google and when it is shared:

* ``<title>`` and ``<meta name="description">`` — missing, too long, too short;
* ``<link rel="canonical">`` — missing, or pointing off the site;
* ``og:title``, ``og:description``, ``og:image``, ``og:url`` — missing;
* ``<meta name="robots" content="noindex">`` on a page the sitemap lists,
  which asks Google to index a page and not to in the same breath.

Site-wide, pages sharing a title or a description are reported as duplicates:
Google picks one of them to show and the rest compete with it.

Every page is fetched through :func:`app.services.sitemaps.fetch`, so nothing
off the site's own host is ever requested.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.mixins import utcnow
from app.models.seo import MetaAudit
from app.services import sitemaps
from app.services.seo_sites import SITES, Site
from app.services.sitemaps import FetchError

logger = logging.getLogger(__name__)

#: Only the head matters, and it comes first; a page is read no further.
MAX_PAGE_BYTES = 512 * 1024
TITLE_MAX = 60
DESCRIPTION_MIN = 50
DESCRIPTION_MAX = 160
OG_TAGS = ("og:title", "og:description", "og:image", "og:url")

#: Issue codes, with the wording the report and the page share.
ISSUES: dict[str, str] = {
    "fetch_failed": "Page could not be fetched",
    "missing_title": "Missing <title>",
    "title_too_long": f"Title longer than {TITLE_MAX} characters",
    "missing_description": "Missing meta description",
    "description_too_short": f"Meta description shorter than {DESCRIPTION_MIN} characters",
    "description_too_long": f"Meta description longer than {DESCRIPTION_MAX} characters",
    "missing_canonical": "Missing canonical URL",
    "canonical_off_site": "Canonical URL points to another host",
    "missing_og_title": "Missing og:title",
    "missing_og_description": "Missing og:description",
    "missing_og_image": "Missing og:image",
    "missing_og_url": "Missing og:url",
    "noindex": "Listed in the sitemap but marked noindex",
    "duplicate_title": "Title shared with other pages",
    "duplicate_description": "Meta description shared with other pages",
}


def _meta(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str | None:
    attrs = {"name": name} if name else {"property": prop}
    tag = soup.find("meta", attrs=attrs)
    if tag is None and prop:
        # Some sites write Open Graph tags with name= instead of property=.
        tag = soup.find("meta", attrs={"name": prop})
    if tag is None:
        return None
    value = (tag.get("content") or "").strip()
    return value or None


def parse_head(html: str) -> dict:
    """The tags the audit reads, from a page's HTML. Missing ones are ``None``."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    canonical = None
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        rel = rel if isinstance(rel, list) else rel.split()
        if "canonical" in [r.lower() for r in rel]:
            canonical = (link.get("href") or "").strip() or None
            break
    robots = (_meta(soup, name="robots") or "").lower()
    return {
        "title": title or None,
        "description": _meta(soup, name="description"),
        "canonical": canonical,
        "og": {tag: _meta(soup, prop=tag) for tag in OG_TAGS},
        "noindex": "noindex" in robots,
    }


def page_issues(site: Site, head: dict) -> list[str]:
    """Issue codes (``missing_title``, ``title_too_long``, …) for one page's head tags."""
    issues = []
    title = head["title"]
    if not title:
        issues.append("missing_title")
    elif len(title) > TITLE_MAX:
        issues.append("title_too_long")
    description = head["description"]
    if not description:
        issues.append("missing_description")
    elif len(description) < DESCRIPTION_MIN:
        issues.append("description_too_short")
    elif len(description) > DESCRIPTION_MAX:
        issues.append("description_too_long")
    canonical = head["canonical"]
    if not canonical:
        issues.append("missing_canonical")
    elif (host := urlsplit(canonical).hostname) and host.lower() != site.domain:
        issues.append("canonical_off_site")
    for tag in OG_TAGS:
        if not head["og"].get(tag):
            issues.append(f"missing_{tag.replace(':', '_')}")
    if head["noindex"]:
        issues.append("noindex")
    return issues


def _duplicates(pages: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        value = page.get(field)
        if value:
            groups[value.strip().lower()].append(page["url"])
    return [
        {"value": next(p[field] for p in pages if p["url"] == urls[0]), "urls": urls}
        for urls in groups.values()
        if len(urls) > 1
    ]


def audit_site(site: Site, *, transport: httpx.BaseTransport | None = None) -> dict:
    """Fetch and audit *site*. Pure network and parsing — touches no session."""
    with sitemaps.http_client(settings.seo_audit_timeout_seconds, transport) as client:
        sitemap_error = None
        try:
            listed = sitemaps.sitemap_urls(client, site)
        except FetchError as exc:
            listed = []
            sitemap_error = str(exc)
        urls = list(dict.fromkeys([site.url, *listed]))[: max(1, settings.seo_audit_max_pages)]
        in_sitemap = set(listed)

        def one(url: str) -> dict:
            try:
                final, html = sitemaps.fetch(client, site, url, max_bytes=MAX_PAGE_BYTES)
            except FetchError as exc:
                return {"url": url, "error": str(exc), "issues": ["fetch_failed"]}
            head = parse_head(html)
            issues = page_issues(site, head)
            if "noindex" in issues and url not in in_sitemap:
                # noindex on a page nobody asked Google to index is a choice.
                issues.remove("noindex")
            return {
                "url": url,
                "final_url": final if final != url else None,
                "title": head["title"],
                "description": head["description"],
                "canonical": head["canonical"],
                "og": head["og"],
                "issues": issues,
            }

        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = list(pool.map(one, urls))

    duplicates = {
        "title": _duplicates(pages, "title"),
        "description": _duplicates(pages, "description"),
    }
    for kind, groups in duplicates.items():
        dup_urls = {u for g in groups for u in g["urls"]}
        for page in pages:
            if page["url"] in dup_urls:
                page["issues"].append(f"duplicate_{kind}")

    counts: dict[str, int] = defaultdict(int)
    for page in pages:
        for issue in page["issues"]:
            counts[issue] += 1
    return {
        "pages": pages,
        "duplicates": duplicates,
        "counts": dict(counts),
        "sitemap_error": sitemap_error,
    }


def run(
    db: Session,
    sites: Iterable[Site] = SITES,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[MetaAudit]:
    """Audit each of *sites* in turn and store the reports. Commits per site,
    so a long sweep that dies part way keeps what it finished."""
    rows = []
    for site in sites:
        try:
            report = audit_site(site, transport=transport)
            error = None
        except Exception as exc:  # noqa: BLE001 — one site must not end the sweep
            logger.exception("meta audit: %s failed", site.key)
            report, error = {"pages": [], "duplicates": {}, "counts": {}}, type(exc).__name__
        row = db.scalar(select(MetaAudit).where(MetaAudit.site_key == site.key))
        if row is None:
            row = MetaAudit(site_key=site.key)
            db.add(row)
        row.report = report
        row.pages_scanned = len(report["pages"])
        row.issue_count = sum(report["counts"].values())
        row.error = error or report.get("sitemap_error")
        row.scanned_at = utcnow()
        db.commit()
        rows.append(row)
    return rows


def summary(db: Session, *, include_pages: bool = True) -> list[dict]:
    """Every site with its latest audit, scanned or not."""
    rows = {r.site_key: r for r in db.scalars(select(MetaAudit)).all()}
    out = []
    for site in SITES:
        r = rows.get(site.key)
        report = (r.report if r else None) or {}
        entry = {
            "key": site.key,
            "name": site.name,
            "domain": site.domain,
            "scanned_at": r.scanned_at if r else None,
            "pages_scanned": r.pages_scanned if r else 0,
            "issue_count": r.issue_count if r else 0,
            "error": r.error if r else None,
            "counts": report.get("counts", {}),
        }
        if include_pages:
            entry["pages"] = report.get("pages", [])
            entry["duplicates"] = report.get("duplicates", {"title": [], "description": []})
        out.append(entry)
    return out
