"""The SEO health dashboard: every DoAide site's search footing on one page.

Joins what the other SEO modules already keep — no new fetches happen here, so
the page loads from the database alone:

* sitemap state per site, from :mod:`app.services.sitemaps`;
* the account's SEO posts (:mod:`app.services.seo_posts`), attributed to a site
  by their project's ``live_url`` — a project whose live URL is on
  ``tax.doaide.com`` writes posts *for* Tax;
* a content calendar of those posts around today.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.project import Project
from app.services import seo_posts, seo_sites, sitemaps

#: The calendar shows this many days before today and after it.
CALENDAR_BACK_DAYS = 7
CALENDAR_AHEAD_DAYS = 28
#: Posts published within this many days count as "recent" on a site's row.
RECENT_DAYS = 30
RECENT_LIMIT = 10


def _site_for_url(url: str | None) -> str | None:
    host = (urlsplit(url or "").hostname or "").lower()
    for site in seo_sites.SITES:
        if host == site.domain:
            return site.key
    return None


def project_sites(db: Session, user_id: int) -> dict[str, str]:
    """``project name → site key`` for the account's projects that live on a DoAide site."""
    rows = db.execute(
        select(Project.name, Project.live_url).where(Project.user_id == user_id)
    ).all()
    out = {}
    for name, live_url in rows:
        key = _site_for_url(live_url)
        if key:
            out[name] = key
    return out


def _day(when: datetime, zone: ZoneInfo) -> date:
    return when.astimezone(zone).date()


def calendar(posts: list[dict], *, today: date, zone: ZoneInfo) -> list[dict]:
    """One entry per day in the window, each with the posts that fall on it.

    A post falls on its publish day if it has gone out, else its scheduled day.
    Days with nothing are included, so the client draws a grid without
    reconstructing the range.
    """
    by_day: dict[date, list[dict]] = defaultdict(list)
    for p in posts:
        when = p["published_at"] or p["scheduled_for"]
        if when is None:
            continue
        by_day[_day(when, zone)].append(
            {"id": p["id"], "title": p["title"], "status": p["status"], "when": when}
        )
    start = today - timedelta(days=CALENDAR_BACK_DAYS)
    days = []
    for offset in range(CALENDAR_BACK_DAYS + CALENDAR_AHEAD_DAYS + 1):
        d = start + timedelta(days=offset)
        days.append(
            {"date": d, "posts": sorted(by_day.get(d, []), key=lambda e: e["when"])}
        )
    return days


def health(db: Session, user_id: int, *, tz: str = "UTC") -> dict:
    try:
        zone = ZoneInfo(tz)
    except (KeyError, ValueError):
        zone = ZoneInfo("UTC")
    now = utcnow()
    posts = seo_posts.queue(db, user_id, limit=seo_posts.CANDIDATE_LIMIT)
    owners = project_sites(db, user_id)

    recent_cutoff = now - timedelta(days=RECENT_DAYS)
    published = sorted(
        (p for p in posts if p["published_at"]), key=lambda p: p["published_at"], reverse=True
    )
    upcoming = [p for p in posts if p["scheduled_for"] and not p["published_at"]]

    per_site: dict[str, dict[str, int]] = defaultdict(lambda: {"recent": 0, "scheduled": 0})
    for p in posts:
        key = owners.get(p["project_name"])
        if not key:
            continue
        if p["published_at"] and p["published_at"] >= recent_cutoff:
            per_site[key]["recent"] += 1
        elif p["scheduled_for"] and not p["published_at"] and p["scheduled_for"] >= now:
            per_site[key]["scheduled"] += 1

    sites = []
    for row in sitemaps.status(db):
        counts = per_site.get(row["key"], {"recent": 0, "scheduled": 0})
        sites.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "key",
                        "name",
                        "domain",
                        "url",
                        "checked",
                        "url_count",
                        "fetch_error",
                        "submit_status",
                        "submit_error",
                        "gsc_submitted",
                        "gsc_indexed",
                        "gsc_errors",
                        "checked_at",
                    )
                },
                "recent_posts": counts["recent"],
                "scheduled_posts": counts["scheduled"],
            }
        )

    totals = {
        "sites": len(sites),
        "sitemaps_submitted": sum(1 for s in sites if s["submit_status"] == "submitted"),
        "sitemap_problems": sum(
            1 for s in sites if s["fetch_error"] or s["submit_status"] == "error"
        ),
        "urls_in_sitemaps": sum(s["url_count"] or 0 for s in sites),
        "indexed_pages": sum(s["gsc_indexed"] or 0 for s in sites),
        "posts_published_30d": sum(1 for p in published if p["published_at"] >= recent_cutoff),
        "posts_scheduled": sum(1 for p in upcoming if p["scheduled_for"] >= now),
    }

    return {
        "generated_at": now,
        "totals": totals,
        "sites": sites,
        "recent_posts": [
            {**p, "site_key": owners.get(p["project_name"])} for p in published[:RECENT_LIMIT]
        ],
        "calendar": calendar(posts, today=now.astimezone(zone).date(), zone=zone),
    }
