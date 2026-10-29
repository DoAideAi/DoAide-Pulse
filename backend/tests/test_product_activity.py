"""The cross-product dashboard: Umami traffic joined with events products report."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import settings
from app.models.mixins import utcnow
from app.models.product_event import ProductEvent
from app.services import product_activity, product_catalog
from app.services.umami import UmamiError
from app.tasks import maintenance_tasks
from app.tasks.celery_app import celery_app

DASH = "/api/v1/products/activity"
INGEST = "/api/v1/products/events"
TOKEN = "ingest-secret-for-tests"


class FakeUmami:
    """Stands in for :class:`app.services.umami.UmamiClient`."""

    def __init__(self, *, configured=True, fail=(), sites=None, events=None):
        self.configured = configured
        self.fail = set(fail)
        self.sites = sites or []
        self.events = events or {}
        self.calls: list[tuple[str, str]] = []

    def _check(self, kind, website_id):
        self.calls.append((kind, website_id))
        if website_id in self.fail:
            raise UmamiError("boom")

    def websites(self):
        return self.sites

    def stats(self, website_id, start_ms, end_ms):
        self._check("stats", website_id)
        return {"pageviews": 100, "visitors": 10, "visits": 12, "bounces": 3, "totaltime": 50}

    def active(self, website_id):
        self._check("active", website_id)
        return 2

    def metrics(self, website_id, start_ms, end_ms, *, type, limit=10):
        self._check(type, website_id)
        if type == "url":
            return [("/", 60), ("/pricing", 20)]
        return list(self.events.get(website_id, {}).items())


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    product_activity.clear_cache()
    monkeypatch.setattr(settings, "product_ingest_token", TOKEN)
    monkeypatch.setattr(settings, "product_activity_admin_emails", "")
    monkeypatch.setattr(settings, "registration_enabled", False)
    monkeypatch.setattr(settings, "umami_website_ids", "")
    yield
    product_activity.clear_cache()


@pytest.fixture
def fake(monkeypatch):
    client = FakeUmami()
    monkeypatch.setattr(product_activity, "get_client", lambda: client)
    return client


def _card(body, key):
    return next(p for p in body["products"] if p["key"] == key)


# ---- ingest ----


def test_a_product_reports_events_and_the_actor_is_masked(client, db):
    resp = client.post(
        INGEST,
        json={"events": [
            {"product": "GST", "kind": "signup", "actor": "Sumit@Example.com"},
            {"product": "prospect", "kind": "action", "name": "email_sent"},
        ]},
        headers={"X-Pulse-Ingest-Token": TOKEN},
    )
    assert resp.status_code == 204, resp.text
    rows = db.query(ProductEvent).order_by(ProductEvent.id).all()
    assert [(r.product, r.kind, r.name, r.actor) for r in rows] == [
        ("gst", "signup", "signup", "S***@example.com"),
        ("prospect", "action", "email_sent", None),
    ]


def test_ingest_needs_the_token(client, db):
    body = {"events": [{"product": "gst", "kind": "login"}]}
    assert client.post(INGEST, json=body).status_code == 401
    bad = client.post(INGEST, json=body, headers={"X-Pulse-Ingest-Token": "nope"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "IngestToken"
    assert db.query(ProductEvent).count() == 0


def test_ingest_is_closed_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "product_ingest_token", "")
    resp = client.post(
        INGEST,
        json={"events": [{"product": "gst", "kind": "login"}]},
        headers={"X-Pulse-Ingest-Token": ""},
    )
    assert resp.status_code == 503


@pytest.mark.parametrize("event", [
    {"product": "nosuch", "kind": "signup"},
    {"product": "gst", "kind": "pageview"},
    {"product": "gst", "kind": "action"},  # an action needs a name
])
def test_ingest_rejects_what_the_dashboard_could_not_show(client, db, event):
    resp = client.post(
        INGEST, json={"events": [event]}, headers={"X-Pulse-Ingest-Token": TOKEN}
    )
    assert resp.status_code == 422
    assert db.query(ProductEvent).count() == 0


def test_a_future_timestamp_is_clamped_to_now(db):
    product_activity.record(db, [{
        "product": "gst", "kind": "login", "occurred_at": utcnow() + timedelta(days=3),
    }])
    row = db.query(ProductEvent).one()
    assert row.occurred_at.replace(tzinfo=None) <= utcnow().replace(tzinfo=None)


@pytest.mark.parametrize("raw,masked", [
    ("a@b.com", "a***@b.com"),
    ("username", "us***"),
    ("   ", None),
    (None, None),
])
def test_mask_actor(raw, masked):
    assert product_activity.mask_actor(raw) == masked


# ---- dashboard ----


def test_every_product_gets_a_card_with_umami_numbers(client, auth, fake):
    resp = client.get(DASH, params={"days": 7}, headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["umami_configured"] is True
    keys = [p["key"] for p in body["products"]]
    assert keys == [p.key for p in product_catalog.PRODUCTS]
    gst = _card(body, "gst")
    assert gst["umami"]["status"] == "ok"
    assert gst["umami"]["pageviews"] == 100
    assert gst["umami"]["active_now"] == 2
    assert gst["umami"]["top_pages"][0] == {"name": "/", "count": 60}
    # Prospect has no id in the catalog and none was discovered.
    assert _card(body, "prospect")["umami"]["status"] == "not_found"
    with_site = sum(1 for p in product_catalog.PRODUCTS if p.website_id)
    assert body["totals"]["pageviews"] == 100 * with_site


def test_key_actions_and_signups_sum_umami_events_and_reports(client, auth, db, monkeypatch):
    gst_id = product_catalog.BY_KEY["gst"].website_id
    fake = FakeUmami(events={gst_id: {"gst_calculation": 5, "signup": 2, "unrelated": 99}})
    monkeypatch.setattr(product_activity, "get_client", lambda: fake)
    product_activity.record(db, [
        {"product": "gst", "kind": "action", "name": "gst_calculate"},
        {"product": "gst", "kind": "signup", "actor": "x@y.com"},
        {"product": "gst", "kind": "login", "actor": "x@y.com"},
    ])

    body = client.get(DASH, headers=auth).json()
    gst = _card(body, "gst")
    calc = next(a for a in gst["key_actions"] if a["label"] == "GST calculations")
    assert calc["count"] == 6
    assert gst["signups"] == 3
    assert gst["logins"] == 1
    assert gst["reported_events"] == 3
    assert [(r["product"], r["kind"], r["actor"]) for r in body["recent"]] == [
        ("gst", "login", "x***@y.com"),
        ("gst", "signup", "x***@y.com"),
    ]
    assert body["recent"][0]["product_name"] == "GST"


def test_old_reports_fall_outside_the_window(client, auth, db, fake):
    product_activity.record(db, [{"product": "realty", "kind": "signup"}])
    row = db.query(ProductEvent).one()
    row.occurred_at = utcnow() - timedelta(days=10)
    db.commit()
    assert _card(client.get(DASH, params={"days": 7}, headers=auth).json(), "realty")["signups"] == 0
    assert _card(client.get(DASH, params={"days": 30}, headers=auth).json(), "realty")["signups"] == 1


def test_one_failing_site_does_not_blank_the_others(client, auth, monkeypatch):
    gst_id = product_catalog.BY_KEY["gst"].website_id
    fake = FakeUmami(fail={gst_id})
    monkeypatch.setattr(product_activity, "get_client", lambda: fake)
    body = client.get(DASH, headers=auth).json()
    assert _card(body, "gst")["umami"]["status"] == "error"
    assert _card(body, "gst")["umami"]["error"] == "boom"
    assert _card(body, "taxfile")["umami"]["status"] == "ok"


def test_unconfigured_umami_still_answers(client, auth, monkeypatch):
    fake = FakeUmami(configured=False)
    monkeypatch.setattr(product_activity, "get_client", lambda: fake)
    body = client.get(DASH, headers=auth).json()
    assert body["umami_configured"] is False
    assert "not configured" in body["umami_error"]
    assert {p["umami"]["status"] for p in body["products"]} == {"unconfigured"}
    assert fake.calls == []


def test_sites_are_discovered_by_domain_and_overrides_win(client, auth, monkeypatch):
    fake = FakeUmami(sites=[{"id": "found-prospect", "name": "P", "domain": "prospect.doaide.com"}])
    monkeypatch.setattr(product_activity, "get_client", lambda: fake)
    monkeypatch.setattr(settings, "umami_website_ids", "gst=override-gst, bogus=1, realty")
    body = client.get(DASH, headers=auth).json()
    assert _card(body, "prospect")["umami"]["website_id"] == "found-prospect"
    assert _card(body, "gst")["umami"]["website_id"] == "override-gst"
    assert _card(body, "realty")["umami"]["website_id"] == product_catalog.BY_KEY["realty"].website_id


def test_results_are_cached_until_a_refresh_is_asked_for(client, auth, fake):
    client.get(DASH, headers=auth)
    first = len(fake.calls)
    client.get(DASH, headers=auth)
    assert len(fake.calls) == first
    client.get(DASH, params={"refresh": "true"}, headers=auth)
    assert len(fake.calls) == 2 * first


def test_the_dashboard_needs_a_signed_in_admin(client, auth, fake, monkeypatch):
    assert client.get(DASH).status_code == 401
    monkeypatch.setattr(settings, "product_activity_admin_emails", "boss@example.com")
    assert client.get(DASH, headers=auth).status_code == 403
    monkeypatch.setattr(settings, "product_activity_admin_emails", "boss@example.com, DEV@example.com")
    assert client.get(DASH, headers=auth).status_code == 200


def test_open_registration_makes_the_admin_list_mandatory(client, auth, fake, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    assert client.get(DASH, headers=auth).status_code == 403


def test_days_is_bounded(client, auth, fake):
    assert client.get(DASH, params={"days": 0}, headers=auth).status_code == 422
    assert client.get(DASH, params={"days": 91}, headers=auth).status_code == 422


# ---- retention ----


def test_old_product_events_are_purged(db, task_session, monkeypatch):
    monkeypatch.setattr(maintenance_tasks, "SessionLocal", task_session)
    product_activity.record(db, [
        {"product": "gst", "kind": "login"},
        {"product": "gst", "kind": "signup"},
    ])
    old = db.query(ProductEvent).filter_by(kind="signup").one()
    old.occurred_at = utcnow() - timedelta(days=settings.product_event_retention_days + 1)
    db.commit()
    assert maintenance_tasks.purge_old_product_events() == {"purged": 1}
    assert [r.kind for r in db.query(ProductEvent).all()] == ["login"]


def test_the_product_event_purge_is_on_the_beat_schedule():
    entry = celery_app.conf.beat_schedule["purge-old-product-events"]
    assert entry["task"] == "app.tasks.maintenance_tasks.purge_old_product_events"


def test_website_id_overrides_parse_leniently():
    assert product_catalog.website_id_overrides(" GST = a ,x=1,bad,realty=") == {"gst": "a"}
