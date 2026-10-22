"""The meta-tag auditor: titles, descriptions, canonicals and Open Graph tags."""
from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.models.seo import MetaAudit
from app.services import meta_audit, seo_sites

URL = "/api/v1/seo/audit"
GST = seo_sites.BY_KEY["gst"]

GOOD_DESC = "Calculate GST, file returns and track input tax credit for your small business."


def page(
    title="GST calculator for India",
    description=GOOD_DESC,
    canonical="https://gst.doaide.com/",
    og=True,
    robots=None,
):
    head = []
    if title is not None:
        head.append(f"<title>{title}</title>")
    if description is not None:
        head.append(f'<meta name="description" content="{description}">')
    if canonical is not None:
        head.append(f'<link rel="canonical" href="{canonical}">')
    if og:
        head += [
            f'<meta property="og:title" content="{title}">',
            f'<meta property="og:description" content="{description}">',
            '<meta property="og:image" content="https://gst.doaide.com/og.png">',
            f'<meta property="og:url" content="{canonical}">',
        ]
    if robots:
        head.append(f'<meta name="robots" content="{robots}">')
    return f"<html><head>{''.join(head)}</head><body>hi</body></html>"


def sitemap(*urls):
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


def transport(pages: dict[str, str]) -> httpx.MockTransport:
    def handler(request):
        body = pages.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="gone")
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "seo_audit_max_pages", 25)
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)


# ---- parsing ----


def test_a_complete_head_has_no_issues():
    head = meta_audit.parse_head(page())
    assert head["title"] == "GST calculator for India"
    assert head["og"]["og:image"] == "https://gst.doaide.com/og.png"
    assert meta_audit.page_issues(GST, head) == []


def test_every_missing_tag_is_named():
    head = meta_audit.parse_head("<html><head></head></html>")
    assert meta_audit.page_issues(GST, head) == [
        "missing_title",
        "missing_description",
        "missing_canonical",
        "missing_og_title",
        "missing_og_description",
        "missing_og_image",
        "missing_og_url",
    ]


def test_lengths_and_an_off_site_canonical_are_flagged():
    head = meta_audit.parse_head(
        page(title="x" * 70, description="Too short.", canonical="https://gst.example.com/")
    )
    issues = meta_audit.page_issues(GST, head)
    assert {"title_too_long", "description_too_short", "canonical_off_site"} <= set(issues)
    long_desc = meta_audit.parse_head(page(description="y" * 200))
    assert "description_too_long" in meta_audit.page_issues(GST, long_desc)


def test_og_tags_written_with_name_still_count_and_rel_is_case_insensitive():
    html = (
        '<head><title>T</title><link rel="Canonical" href="https://gst.doaide.com/">'
        '<meta name="og:title" content="T"></head>'
    )
    head = meta_audit.parse_head(html)
    assert head["canonical"] == "https://gst.doaide.com/"
    assert head["og"]["og:title"] == "T"


# ---- a site ----


def test_a_site_audit_reports_pages_duplicates_and_noindex():
    pages = {
        GST.sitemap_url: sitemap(
            "https://gst.doaide.com/",
            "https://gst.doaide.com/a",
            "https://gst.doaide.com/b",
            "https://gst.doaide.com/hidden",
            "https://gst.doaide.com/dead",
        ),
        "https://gst.doaide.com/": page(),
        "https://gst.doaide.com/a": page(title="Same", canonical="https://gst.doaide.com/a"),
        "https://gst.doaide.com/b": page(title="same ", canonical="https://gst.doaide.com/b"),
        "https://gst.doaide.com/hidden": page(
            title="Hidden", description="Hidden page description that is long enough to pass.",
            canonical="https://gst.doaide.com/hidden", robots="noindex, follow",
        ),
    }
    report = meta_audit.audit_site(GST, transport=transport(pages))

    by_url = {p["url"]: p for p in report["pages"]}
    assert len(by_url) == 5
    assert by_url["https://gst.doaide.com/dead"]["issues"] == ["fetch_failed"]
    assert "noindex" in by_url["https://gst.doaide.com/hidden"]["issues"]
    assert "duplicate_title" in by_url["https://gst.doaide.com/a"]["issues"]
    assert "duplicate_title" not in by_url["https://gst.doaide.com/hidden"]["issues"]
    # The homepage, /a and /b share GOOD_DESC.
    assert len(report["duplicates"]["description"][0]["urls"]) == 3
    assert report["counts"]["duplicate_title"] == 2
    assert report["sitemap_error"] is None


def test_without_a_sitemap_the_homepage_is_still_audited():
    report = meta_audit.audit_site(GST, transport=transport({"https://gst.doaide.com/": page()}))
    assert [p["url"] for p in report["pages"]] == ["https://gst.doaide.com/"]
    assert "404" in report["sitemap_error"]


def test_the_page_cap_holds_and_the_homepage_comes_first(monkeypatch):
    monkeypatch.setattr(settings, "seo_audit_max_pages", 2)
    urls = [f"https://gst.doaide.com/p{i}" for i in range(10)]
    pages = {GST.sitemap_url: sitemap(*urls), **{u: page(title=u) for u in urls}}
    report = meta_audit.audit_site(GST, transport=transport(pages))
    assert [p["url"] for p in report["pages"]] == ["https://gst.doaide.com/", urls[0]]


def test_run_stores_one_row_per_site_and_overwrites_it(db):
    t = transport({"https://gst.doaide.com/": page(title=None)})
    meta_audit.run(db, [GST], transport=t)
    meta_audit.run(db, [GST], transport=t)
    row = db.query(MetaAudit).one()
    assert row.pages_scanned == 1
    assert row.issue_count >= 1
    assert row.report["counts"]["missing_title"] == 1


def test_one_broken_site_does_not_end_the_sweep(db, monkeypatch):
    real = meta_audit.audit_site

    def flaky(site, *, transport=None):
        if site.key == "gst":
            raise RuntimeError("parser exploded")
        return real(site, transport=transport)

    monkeypatch.setattr(meta_audit, "audit_site", flaky)
    rows = meta_audit.run(db, [GST, seo_sites.BY_KEY["tax"]], transport=transport({}))
    assert rows[0].error == "RuntimeError"
    assert rows[1].error and "404" in rows[1].error


# ---- API ----


def test_the_audit_lists_every_site_and_the_issue_wording(client, auth):
    body = client.get(URL, headers=auth).json()
    assert len(body["sites"]) == 14
    assert body["issue_labels"]["missing_og_image"] == "Missing og:image"
    assert body["sites"][0]["scanned_at"] is None


def test_auditing_one_site_runs_in_the_request(client, auth, monkeypatch):
    real = meta_audit.run
    monkeypatch.setattr(
        meta_audit,
        "run",
        lambda db, sites: real(db, sites, transport=transport({"https://gst.doaide.com/": page()})),
    )
    resp = client.post(f"{URL}?site=gst", headers=auth)
    assert resp.status_code == 200
    gst = next(s for s in resp.json()["sites"] if s["key"] == "gst")
    assert gst["pages_scanned"] == 1
    assert gst["pages"][0]["title"] == "GST calculator for India"
    assert client.post(f"{URL}?site=nope", headers=auth).status_code == 404


def test_auditing_everything_is_queued(client, auth, monkeypatch):
    from app.tasks import seo_tasks

    ran = []
    monkeypatch.setattr(seo_tasks, "audit_meta_tags", lambda: ran.append(True))
    resp = client.post(URL, headers=auth)
    assert resp.status_code == 202
    assert resp.json() == {"queued": True}
    assert ran == [True]  # Celery is off in tests, so it ran after the response


def test_the_health_dashboard_carries_audit_issue_counts(client, auth, db):
    meta_audit.run(db, [GST], transport=transport({"https://gst.doaide.com/": page(title=None)}))
    body = client.get("/api/v1/seo/health", headers=auth).json()
    gst = next(s for s in body["sites"] if s["key"] == "gst")
    tax = next(s for s in body["sites"] if s["key"] == "tax")
    assert gst["meta_issues"] >= 1
    assert tax["meta_issues"] is None
    assert body["totals"]["meta_issues"] == gst["meta_issues"]
