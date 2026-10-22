"""The SEO health dashboard: sitemaps, posts per site and the calendar, from the database."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.project import Project
from app.models.seo import SitemapStatus
from app.services import seo_health

URL = "/api/v1/seo/health"


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


def _post(db, project, title, **extra):
    row = Content(
        project_id=project.id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        body_markdown="Body",
        tags=["seo"],
        content_type=ContentType.HOW_TO,
        **extra,
    )
    db.add(row)
    db.commit()
    return row


def test_the_dashboard_joins_sitemaps_posts_and_the_calendar(client, auth, db, user):
    now = utcnow()
    tax = Project(
        user_id=user.id,
        name="Tax",
        slug="tax",
        description="d",
        live_url="https://tax.doaide.com/app",
    )
    elsewhere = Project(
        user_id=user.id, name="Side", slug="side", description="d", live_url="https://x.test"
    )
    db.add_all([tax, elsewhere])
    db.commit()
    _post(
        db, tax, "Live one", status=ContentStatus.PUBLISHED, published_at=now - timedelta(days=2)
    )
    _post(
        db, tax, "Old one", status=ContentStatus.PUBLISHED, published_at=now - timedelta(days=60)
    )
    _post(
        db, tax, "Next week", status=ContentStatus.APPROVED, scheduled_for=now + timedelta(days=7)
    )
    _post(
        db,
        elsewhere,
        "Unattributed",
        status=ContentStatus.APPROVED,
        scheduled_for=now + timedelta(days=3),
    )
    db.add_all(
        [
            SitemapStatus(
                site_key="tax",
                sitemap_url="https://tax.doaide.com/sitemap.xml",
                url_count=40,
                submit_status="submitted",
                gsc_submitted=40,
                gsc_indexed=31,
                checked_at=now,
            ),
            SitemapStatus(
                site_key="comply",
                sitemap_url="https://comply.doaide.com/sitemap.xml",
                fetch_error="answered 404",
                submit_status="error",
                checked_at=now,
            ),
        ]
    )
    db.commit()

    resp = client.get(URL, headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["totals"] == {
        "sites": 14,
        "sitemaps_submitted": 1,
        "sitemap_problems": 1,
        "urls_in_sitemaps": 40,
        "indexed_pages": 31,
        "posts_published_30d": 1,
        "posts_scheduled": 2,
    }
    tax_row = next(s for s in body["sites"] if s["key"] == "tax")
    assert tax_row["recent_posts"] == 1 and tax_row["scheduled_posts"] == 1
    assert [p["title"] for p in body["recent_posts"]] == ["Live one", "Old one"]
    assert body["recent_posts"][0]["site_key"] == "tax"

    days = body["calendar"]
    assert len(days) == seo_health.CALENDAR_BACK_DAYS + seo_health.CALENDAR_AHEAD_DAYS + 1
    titles = [p["title"] for d in days for p in d["posts"]]
    assert set(titles) == {"Live one", "Next week", "Unattributed"}


def test_calendar_days_follow_the_requested_zone():
    # 20:00 UTC on the 1st is already the 2nd in Kolkata.

    when = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    post = {
        "id": 1,
        "title": "t",
        "status": "approved",
        "published_at": None,
        "scheduled_for": when,
    }
    utc = seo_health.calendar([post], today=date(2026, 11, 1), zone=ZoneInfo("UTC"))
    ist = seo_health.calendar([post], today=date(2026, 11, 1), zone=ZoneInfo("Asia/Kolkata"))

    def day_of(days):
        return next(d["date"] for d in days if d["posts"])

    assert day_of(utc) == date(2026, 11, 1)
    assert day_of(ist) == date(2026, 11, 2)


def test_an_unknown_zone_falls_back_to_utc(client, auth):
    assert client.get(f"{URL}?tz=Not/AZone", headers=auth).status_code == 200


def test_the_dashboard_is_for_product_admins(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "boss@example.com")
    assert client.get(URL, headers=auth).status_code == 403
