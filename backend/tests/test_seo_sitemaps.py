"""Sitemaps for every DoAide site: fetched by Pulse, submitted to Search Console."""
from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.models.seo import SitemapStatus
from app.services import search_console, seo_sites, sitemaps
from app.services.search_console import SearchConsoleClient, SearchConsoleError

URL = "/api/v1/seo/sitemaps"

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://gst.doaide.com/</loc></url>
  <url><loc>https://gst.doaide.com/blog/gst-rates?a=1&amp;b=2</loc></url>
  <url><loc>https://evil.example.com/elsewhere</loc></url>
</urlset>"""

INDEX = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://gst.doaide.com/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>http://169.254.169.254/latest</loc></sitemap>
</sitemapindex>"""


class FakeGSC:
    def __init__(self, *, configured=True, fail=False):
        self.configured = configured
        self.client_email = "pulse@doaide.iam.gserviceaccount.com" if configured else None
        self.fail = fail
        self.submitted: list[tuple[str, str]] = []

    def submit(self, site_url, feedpath):
        if self.fail:
            raise SearchConsoleError("Search Console refused: add it as an Owner")
        self.submitted.append((site_url, feedpath))

    def sitemap(self, site_url, feedpath):
        return {
            "submitted": 3,
            "indexed": 2,
            "last_submitted": "2026-10-22T00:00:00Z",
            "last_downloaded": "2026-10-21T00:00:00Z",
            "is_pending": False,
            "errors": 0,
            "warnings": 1,
        }


def _sites_transport(pages: dict[str, tuple[int, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        code, body = pages.get(str(request.url), (404, "not here"))
        return httpx.Response(code, text=body)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _no_property_override(monkeypatch):
    monkeypatch.setattr(settings, "gsc_site_url", "")
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


# ---- parsing and fetching ----


def test_locations_are_unescaped_and_an_index_is_recognised():
    assert sitemaps.parse_locs(SITEMAP) == (
        False,
        [
            "https://gst.doaide.com/",
            "https://gst.doaide.com/blog/gst-rates?a=1&b=2",
            "https://evil.example.com/elsewhere",
        ],
    )
    assert sitemaps.parse_locs(INDEX)[0] is True


def test_only_the_sites_own_https_urls_are_counted():
    site = seo_sites.BY_KEY["gst"]
    transport = _sites_transport({site.sitemap_url: (200, SITEMAP)})
    with sitemaps.http_client(5, transport) as client:
        urls = sitemaps.sitemap_urls(client, site)
    assert urls == ["https://gst.doaide.com/", "https://gst.doaide.com/blog/gst-rates?a=1&b=2"]


def test_an_index_is_followed_but_never_off_the_site():
    site = seo_sites.BY_KEY["gst"]
    asked: list[str] = []

    def handler(request):
        asked.append(str(request.url))
        if str(request.url) == site.sitemap_url:
            return httpx.Response(200, text=INDEX)
        return httpx.Response(200, text=SITEMAP)

    with sitemaps.http_client(5, httpx.MockTransport(handler)) as client:
        urls = sitemaps.sitemap_urls(client, site)
    assert len(urls) == 2
    assert not any("169.254" in u for u in asked)


def test_a_redirect_off_the_site_is_refused():
    site = seo_sites.BY_KEY["gst"]

    def handler(request):
        if request.url.host == "gst.doaide.com":
            return httpx.Response(302, headers={"Location": "https://other.example.com/x"})
        return httpx.Response(200, text=SITEMAP)

    with (
        sitemaps.http_client(5, httpx.MockTransport(handler)) as client,
        pytest.raises(sitemaps.FetchError, match="redirected off"),
    ):
        sitemaps.fetch(client, site, site.sitemap_url, max_bytes=1000)


# ---- check() ----


def test_check_records_counts_submission_and_googles_numbers(db):
    gsc = FakeGSC()
    site = seo_sites.BY_KEY["gst"]
    rows = sitemaps.check(
        db, [site], gsc=gsc, transport=_sites_transport({site.sitemap_url: (200, SITEMAP)})
    )
    row = rows[0]
    assert row.url_count == 2
    assert row.fetch_error is None
    assert row.submit_status == "submitted"
    assert row.gsc_submitted == 3 and row.gsc_indexed == 2 and row.gsc_warnings == 1
    assert row.submitted_at is not None
    assert gsc.submitted == [("https://gst.doaide.com/", "https://gst.doaide.com/sitemap.xml")]


def test_a_domain_property_is_used_when_configured(db, monkeypatch):
    monkeypatch.setattr(settings, "gsc_site_url", "sc-domain:doaide.com")
    gsc = FakeGSC()
    site = seo_sites.BY_KEY["khata"]
    sitemaps.check(db, [site], gsc=gsc, transport=_sites_transport({}))
    assert gsc.submitted == [("sc-domain:doaide.com", "https://khata.doaide.com/sitemap.xml")]


def test_a_missing_sitemap_is_still_submitted_and_both_problems_kept(db):
    gsc = FakeGSC(fail=True)
    site = seo_sites.BY_KEY["comply"]
    row = sitemaps.check(db, [site], gsc=gsc, transport=_sites_transport({}))[0]
    assert row.url_count is None
    assert "404" in row.fetch_error
    assert row.submit_status == "error"
    assert "Owner" in row.submit_error


def test_without_a_service_account_nothing_is_submitted(db):
    site = seo_sites.BY_KEY["tax"]
    row = sitemaps.check(
        db,
        [site],
        gsc=FakeGSC(configured=False),
        transport=_sites_transport({site.sitemap_url: (200, SITEMAP)}),
    )[0]
    assert row.submit_status == "unconfigured"
    assert row.url_count == 0  # the fixture's URLs are gst's, not tax's


def test_a_second_check_updates_the_same_row(db):
    site = seo_sites.BY_KEY["gst"]
    gsc = FakeGSC()
    sitemaps.check(db, [site], gsc=gsc, transport=_sites_transport({}))
    sitemaps.check(
        db, [site], gsc=gsc, transport=_sites_transport({site.sitemap_url: (200, SITEMAP)})
    )
    assert db.query(SitemapStatus).count() == 1
    assert db.query(SitemapStatus).one().url_count == 2


# ---- API ----


def test_every_catalog_site_is_listed_before_any_check(client, auth, monkeypatch):
    monkeypatch.setattr(search_console, "get_client", lambda: FakeGSC(configured=False))
    resp = client.get(URL, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["gsc_configured"] is False
    domains = [s["domain"] for s in body["sites"]]
    assert len(domains) == 14
    assert "cortex.doaide.com" in domains and "desk.doaide.com" in domains
    assert {s["submit_status"] for s in body["sites"]} == {"pending"}


def test_submit_one_site_through_the_api(client, auth, monkeypatch):
    gsc = FakeGSC()
    monkeypatch.setattr(search_console, "get_client", lambda: gsc)
    real_check = sitemaps.check
    monkeypatch.setattr(
        sitemaps,
        "check",
        lambda db, targets: real_check(db, targets, gsc=gsc, transport=_sites_transport({})),
    )
    resp = client.post(f"{URL}/submit?site=desk", headers=auth)
    assert resp.status_code == 200
    desk = next(s for s in resp.json()["sites"] if s["key"] == "desk")
    assert desk["submit_status"] == "submitted"
    assert resp.json()["gsc_account"] == gsc.client_email
    assert client.post(f"{URL}/submit?site=nope", headers=auth).status_code == 404


def test_the_sitemaps_api_is_for_product_admins_only(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "product_activity_admin_emails", "someone-else@example.com")
    assert client.get(URL, headers=auth).status_code == 403
    assert client.get(URL).status_code == 401


def test_the_weekly_task_is_scheduled():
    from app.tasks.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["submit-sitemaps"]
    assert entry["task"] == "app.tasks.seo_tasks.submit_sitemaps"


# ---- the Search Console client ----


@pytest.fixture(scope="module")
def service_account():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "client_email": "pulse@doaide.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }, key.public_key()


def test_the_client_exchanges_a_signed_jwt_and_reuses_the_token(service_account):
    info, public_key = service_account
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            claims = jwt.decode(
                form["assertion"][0],
                public_key,
                algorithms=["RS256"],
                audience="https://oauth2.googleapis.com/token",
            )
            assert claims["iss"] == info["client_email"]
            assert claims["scope"] == search_console.SCOPE
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        if request.method == "PUT":
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "lastDownloaded": "2026-10-20T00:00:00Z",
                "contents": [{"type": "web", "submitted": "40", "indexed": "31"}],
            },
        )

    gsc = SearchConsoleClient(info, transport=httpx.MockTransport(handler))
    gsc.submit("https://gst.doaide.com/", "https://gst.doaide.com/sitemap.xml")
    got = gsc.sitemap("https://gst.doaide.com/", "https://gst.doaide.com/sitemap.xml")

    assert got["submitted"] == 40 and got["indexed"] == 31
    assert sum(1 for c in calls if c.url.host == "oauth2.googleapis.com") == 1
    put = next(c for c in calls if c.method == "PUT")
    assert "https%3A%2F%2Fgst.doaide.com%2F" in put.url.raw_path.decode()


def test_a_403_says_to_add_the_account_as_owner(service_account):
    info, _ = service_account

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(403, json={"error": {"message": "nope"}})

    gsc = SearchConsoleClient(info, transport=httpx.MockTransport(handler))
    with pytest.raises(SearchConsoleError, match="Owner"):
        gsc.submit("https://gst.doaide.com/", "https://gst.doaide.com/sitemap.xml")


def test_the_service_account_loads_from_inline_json_or_a_file(tmp_path, monkeypatch):
    blob = {"client_email": "a@b.iam.gserviceaccount.com", "private_key": "k"}
    monkeypatch.setattr(settings, "gsc_service_account_json", json.dumps(blob))
    assert search_console.load_service_account() == blob

    path = tmp_path / "sa.json"
    path.write_text(json.dumps(blob))
    monkeypatch.setattr(settings, "gsc_service_account_json", "")
    monkeypatch.setattr(settings, "gsc_service_account_file", str(path))
    assert search_console.load_service_account() == blob

    path.write_text("{not json")
    assert search_console.load_service_account() is None


def test_an_unconfigured_client_refuses_before_touching_the_network():
    gsc = SearchConsoleClient(None)
    assert not gsc.configured
    with pytest.raises(search_console.SearchConsoleNotConfigured):
        gsc.submit("https://gst.doaide.com/", "x")
