"""SEO traffic: Umami pages and referrers per site, tied back to Pulse content."""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.project import Project
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import product_activity, seo_traffic
from app.services.umami import UmamiError

URL = "/api/v1/seo/traffic"


class FakeUmami:
    def __init__(self, *, configured=True, sites=None, fail=(), no_referrers=False):
        self.configured = configured
        self.sites = sites or []
        self.fail = set(fail)
        self.no_referrers = no_referrers
        self.calls = 0

    def websites(self):
        return self.sites

    def stats(self, website_id, start_ms, end_ms):
        self.calls += 1
        if website_id in self.fail:
            raise UmamiError("boom")
        return {"pageviews": 500, "visitors": 120, "visits": 150, "bounces": 1, "totaltime": 2}

    def metrics(self, website_id, start_ms, end_ms, *, type, limit=10):
        if type == "url":
            return [
                ("/", 300),
                ("/blog/file-itr-online", 120),
                ("/guides/gst-basics/", 40),
                ("/blog", 20),
                ("/pricing", 20),
            ]
        if self.no_referrers:
            raise UmamiError("no referrer metric")
        return [("www.google.com", 90), ("bing.com", 10), ("t.co", 25)]


SITES = [
    {"id": "tax-id", "name": "Tax", "domain": "tax.doaide.com"},
    {"id": "gst-id", "name": "GST", "domain": "gst.doaide.com"},
]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    seo_traffic.clear_cache()
    product_activity.clear_cache()
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)
    yield
    seo_traffic.clear_cache()
    product_activity.clear_cache()


@pytest.fixture
def fake(monkeypatch):
    client = FakeUmami(sites=SITES)
    monkeypatch.setattr(seo_traffic, "get_client", lambda: client)
    return client


def test_search_engines_are_recognised():
    assert seo_traffic.is_search_engine("www.google.com")
    assert seo_traffic.is_search_engine("https://duckduckgo.com/")
    assert seo_traffic.is_search_engine("google.co.in")
    assert not seo_traffic.is_search_engine("notgoogle.com")
    assert not seo_traffic.is_search_engine("t.co")


def test_traffic_ties_pages_to_pulse_content(client, auth, db, user, fake):
    project = Project(user_id=user.id, name="Tax", slug="tax", description="d")
    db.add(project)
    db.commit()
    piece = Content(
        project_id=project.id,
        title="File ITR online",
        slug="file-itr-online",
        content_type=ContentType.HOW_TO,
        status=ContentStatus.PUBLISHED,
        canonical_url="https://tax.doaide.com/blog/file-itr-online/",
    )
    other = Content(
        project_id=project.id,
        title="GST basics",
        slug="gst-basics",
        content_type=ContentType.HOW_TO,
        status=ContentStatus.PUBLISHED,
    )
    db.add_all([piece, other])
    db.commit()
    db.add(
        Publication(
            content_id=other.id,
            platform=Platform.GIT,
            status=PublicationStatus.PUBLISHED,
            external_url="https://gst.doaide.com/guides/gst-basics",
        )
    )
    db.commit()

    resp = client.get(f"{URL}?days=7", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["umami_configured"] is True
    assert body["days"] == 7

    tax = next(s for s in body["sites"] if s["key"] == "tax")
    assert tax["status"] == "ok"
    assert tax["pageviews"] == 500
    assert tax["search_visits"] == 100
    blog = next(p for p in tax["top_pages"] if p["path"] == "/blog/file-itr-online")
    assert blog["content_id"] == piece.id and blog["title"] == "File ITR online"
    assert blog["url"] == "https://tax.doaide.com/blog/file-itr-online"
    assert not next(p for p in tax["top_pages"] if p["path"] == "/blog")["is_content"]
    assert not next(p for p in tax["top_pages"] if p["path"] == "/")["is_content"]

    gst = next(s for s in body["sites"] if s["key"] == "gst")
    guide = next(p for p in gst["top_pages"] if p["path"] == "/guides/gst-basics/")
    assert guide["content_id"] == other.id
    # The tax guide is Tax's content, not GST's: content is matched per host.
    assert next(p for p in gst["top_pages"] if p["path"] == "/blog/file-itr-online")[
        "content_id"
    ] is None

    top = body["top_content"]
    assert top[0]["views"] == 120
    assert {(t["site_key"], t["path"]) for t in top} == {
        ("tax", "/blog/file-itr-online"),
        ("tax", "/guides/gst-basics/"),
        ("gst", "/blog/file-itr-online"),
        ("gst", "/guides/gst-basics/"),
    }
    assert body["totals"] == {"pageviews": 1000, "visitors": 240, "search_visits": 200}

    # Sites Umami does not know are listed, last, with why.
    cortex = next(s for s in body["sites"] if s["key"] == "cortex")
    assert cortex["status"] == "not_found"
    assert body["sites"][-1]["status"] != "ok"


def test_someone_elses_content_is_not_matched(client, auth, db, fake):
    from app.models.user import User

    stranger = User(email="s@example.com", full_name="S", hashed_password="x")
    db.add(stranger)
    db.commit()
    theirs = Project(user_id=stranger.id, name="T", slug="t", description="d")
    db.add(theirs)
    db.commit()
    db.add(
        Content(
            project_id=theirs.id,
            title="Theirs",
            slug="theirs",
            content_type=ContentType.HOW_TO,
            canonical_url="https://tax.doaide.com/blog/file-itr-online",
        )
    )
    db.commit()
    body = client.get(URL, headers=auth).json()
    tax = next(s for s in body["sites"] if s["key"] == "tax")
    assert all(p["content_id"] is None for p in tax["top_pages"])


def test_one_failing_site_keeps_its_card_and_referrers_are_optional(client, auth, monkeypatch):
    umami = FakeUmami(sites=SITES, fail={"gst-id"}, no_referrers=True)
    monkeypatch.setattr(seo_traffic, "get_client", lambda: umami)
    body = client.get(URL, headers=auth).json()
    gst = next(s for s in body["sites"] if s["key"] == "gst")
    tax = next(s for s in body["sites"] if s["key"] == "tax")
    assert gst["status"] == "error" and gst["error"] == "boom"
    assert tax["status"] == "ok" and tax["referrers"] == []


def test_answers_are_cached_until_refresh(client, auth, fake):
    client.get(URL, headers=auth)
    first = fake.calls
    client.get(URL, headers=auth)
    assert fake.calls == first
    client.get(f"{URL}?refresh=true", headers=auth)
    assert fake.calls == first * 2


def test_unconfigured_umami_says_so(client, auth, monkeypatch):
    monkeypatch.setattr(seo_traffic, "get_client", lambda: FakeUmami(configured=False))
    body = client.get(URL, headers=auth).json()
    assert body["umami_configured"] is False
    assert "UMAMI_USERNAME" in body["umami_error"]
    assert body["sites"] == []


def test_traffic_is_for_product_admins(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "boss@example.com")
    assert client.get(URL, headers=auth).status_code == 403
