"""A failing Umami is not asked again on every dashboard load.

The dashboards cache Umami's answers for ``umami_cache_seconds``, but only the
good ones. A failure went uncached, so with Umami down every load of the
products dashboard asked it again — four calls per product, eight products in
parallel, each waiting out its eight-second timeout — and so did every load of
the SEO traffic view. A page that answered in a moment took half a minute, on
every refresh, while it kept hammering the service that was struggling.

A failure is now kept for a short while (``ERROR_CACHE_SECONDS``), shorter than a
good answer so recovery shows quickly. Forcing a refresh still asks at once.
"""
from __future__ import annotations

import pytest

from app.services import product_activity, seo_traffic
from app.services.product_catalog import PRODUCTS
from app.services.seo_sites import SITES
from app.services.umami import UmamiError


class _DownUmami:
    def __init__(self):
        self.calls = 0

    def stats(self, *a, **k):
        self.calls += 1
        raise UmamiError("timed out")

    def metrics(self, *a, **k):  # pragma: no cover - stats fails first
        raise UmamiError("timed out")

    def active(self, *a, **k):  # pragma: no cover - stats fails first
        raise UmamiError("timed out")


@pytest.fixture(autouse=True)
def _fresh_caches():
    product_activity.clear_cache()
    seo_traffic.clear_cache()
    yield
    product_activity.clear_cache()
    seo_traffic.clear_cache()


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    for module in (product_activity, seo_traffic):
        monkeypatch.setattr(module.time, "monotonic", lambda: now["t"])
    return now


def test_the_products_dashboard_does_not_retry_a_failure_on_the_next_load(clock):
    client = _DownUmami()
    product = PRODUCTS[0]

    first = product_activity._umami_for(client, product, "site-1", 30, force=False)
    second = product_activity._umami_for(client, product, "site-1", 30, force=False)

    assert first["status"] == second["status"] == "error"
    assert client.calls == 1


def test_a_cached_failure_expires_sooner_than_a_good_answer(clock):
    client = _DownUmami()
    product = PRODUCTS[0]
    product_activity._umami_for(client, product, "site-1", 30, force=False)

    clock["t"] += product_activity.ERROR_CACHE_SECONDS + 1
    product_activity._umami_for(client, product, "site-1", 30, force=False)

    assert client.calls == 2
    assert product_activity.settings.umami_cache_seconds > product_activity.ERROR_CACHE_SECONDS


def test_forcing_a_refresh_asks_again_at_once(clock):
    client = _DownUmami()
    product = PRODUCTS[0]
    product_activity._umami_for(client, product, "site-1", 30, force=False)

    product_activity._umami_for(client, product, "site-1", 30, force=True)

    assert client.calls == 2


def test_the_seo_traffic_view_keeps_a_failure_too(clock):
    client = _DownUmami()
    site = SITES[0]

    seo_traffic._site_traffic(client, site, "site-1", 30)
    seo_traffic._site_traffic(client, site, "site-1", 30)

    assert client.calls == 1
