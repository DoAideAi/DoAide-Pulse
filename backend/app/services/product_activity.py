"""The cross-product activity dashboard: Umami traffic plus product-reported events.

Two sources, joined per product from :mod:`app.services.product_catalog`:

* **Umami** — page views, visitors, visits, live visitors, top pages and any
  custom events, for the product's site. Fetched in parallel across products
  and reused for ``umami_cache_seconds`` so an auto-refreshing tab is one
  request per product per minute, not one per tab per minute.
* **Reported events** — :class:`app.models.product_event.ProductEvent` rows the
  products' backends post to Pulse: signups, logins, key actions.

A product whose Umami call fails still gets its card, with its own error, and
its reported events — one site misconfigured in Umami must not blank the page.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.mixins import as_aware, utcnow
from app.models.product_event import ACTION, LOGIN, SIGNUP, ProductEvent
from app.services import product_catalog
from app.services.product_catalog import LOGIN_EVENTS, PRODUCTS, SIGNUP_EVENTS, Product
from app.services.umami import UmamiClient, UmamiError, UmamiNotConfigured, get_client

logger = logging.getLogger(__name__)

#: How many rows the "recent signups and logins" feed shows.
RECENT_LIMIT = 25
#: How many of a product's pages its card lists.
TOP_PAGES = 5
#: How many custom events are asked of Umami per product. Generous: the key
#: actions are matched by name out of this list.
EVENT_LIMIT = 100


# ---- recording ----


def mask_actor(actor: str | None) -> str | None:
    """Enough of an identifier to tell two signups apart, not enough to contact.

    ``sumit@example.com`` → ``s***@example.com``; anything else keeps its first
    two characters. Applied before the row is written, so the unmasked value
    is never in Pulse's database.
    """
    if not actor:
        return None
    actor = actor.strip()
    if not actor:
        return None
    local, at, domain = actor.partition("@")
    if at and local and domain:
        return f"{local[0]}***@{domain.lower()}"[:120]
    return f"{actor[:2]}***"


def record(db: Session, events: Iterable[dict]) -> int:
    """Append reported *events*. Commits. Returns how many were written.

    A timestamp in the future is the product's clock being wrong, not the event
    being early; it is clamped to now so it cannot sit at the top of the feed.
    """
    now = utcnow()
    rows = []
    for event in events:
        occurred = event.get("occurred_at")
        occurred = min(as_aware(occurred), now) if occurred else now
        kind = event["kind"]
        rows.append(
            ProductEvent(
                product=event["product"],
                kind=kind,
                name=event.get("name") or kind,
                actor=mask_actor(event.get("actor")),
                occurred_at=occurred,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


def purge(db: Session, *, days: int) -> int:
    """Delete product events older than ``days``; returns how many went."""
    cutoff = utcnow() - timedelta(days=days)
    result = db.execute(delete(ProductEvent).where(ProductEvent.occurred_at < cutoff))
    db.commit()
    return result.rowcount or 0


# ---- Umami, cached ----

_cache: dict[tuple, tuple[float, dict]] = {}

#: How long a failed Umami answer is kept. Not caching failures at all meant a
#: dashboard load during an outage asked again for every product, each call
#: waiting out ``umami_timeout_seconds``, on every refresh. Shorter than a good
#: answer's ``umami_cache_seconds`` so a recovery shows up quickly; shared with
#: :mod:`app.services.seo_traffic`, which reads the same Umami.
ERROR_CACHE_SECONDS = 15


def cache_seconds_for(result: dict) -> float:
    """How long *result* may be served from the cache: briefly, if it is a failure."""
    ttl = settings.umami_cache_seconds
    return min(ERROR_CACHE_SECONDS, ttl) if result.get("status") == "error" else ttl
_cache_lock = threading.Lock()
_sites: tuple[float, dict[str, str]] | None = None


def clear_cache() -> None:
    """Forget every cached Umami answer, including the site list."""
    global _sites
    with _cache_lock:
        _cache.clear()
        _sites = None


def _site_ids(client: UmamiClient) -> dict[str, str]:
    """Umami's own ``domain → id`` map, refreshed with the same TTL.

    A failure here is not fatal: the catalog's ids still work, which is the
    point of keeping them.
    """
    global _sites
    ttl = settings.umami_cache_seconds
    with _cache_lock:
        if _sites and time.monotonic() - _sites[0] < ttl:
            return _sites[1]
    try:
        mapping = {s["domain"]: s["id"] for s in client.websites() if s["domain"]}
    except UmamiNotConfigured:
        raise
    except UmamiError as exc:
        logger.warning("umami: could not list websites: %s", exc)
        mapping = {}
    with _cache_lock:
        _sites = (time.monotonic(), mapping)
    return mapping


def website_ids(client: UmamiClient) -> dict[str, str]:
    """Umami's ``domain → website id`` map, cached as the dashboard caches it.

    Public for the SEO traffic view, which reads the same Umami for a different
    list of sites and should not list them a second time.
    """
    return _site_ids(client)


def resolve_website_id(product: Product, sites: dict[str, str]) -> str:
    """Override, then Umami's own record for the domain, then the catalog."""
    override = product_catalog.website_id_overrides(settings.umami_website_ids)
    return override.get(product.key) or sites.get(product.domain) or product.website_id


def _umami_for(
    client: UmamiClient, product: Product, website_id: str, days: int, *, force: bool
) -> dict:
    key = (product.key, website_id, days)
    if not force:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < cache_seconds_for(hit[1]):
            return hit[1]

    if not website_id:
        return {"status": "not_found", "error": f"No Umami site for {product.domain}"}

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 86_400_000
    try:
        stats = client.stats(website_id, start_ms, end_ms)
        active = client.active(website_id)
        pages = client.metrics(website_id, start_ms, end_ms, type="url", limit=TOP_PAGES)
        try:
            events = client.metrics(
                website_id, start_ms, end_ms, type="event", limit=EVENT_LIMIT
            )
        except UmamiError:
            # Older instances without event metrics still have traffic worth
            # showing; the event counts are simply absent.
            events = []
    except UmamiError as exc:
        logger.warning("umami: %s (%s) failed: %s", product.key, website_id, exc)
        failed = {"status": "error", "error": str(exc)}
        with _cache_lock:
            _cache[key] = (time.monotonic(), failed)
        return failed

    result = {
        "status": "ok",
        "website_id": website_id,
        **stats,
        "active_now": active,
        "top_pages": [{"name": n, "count": c} for n, c in pages],
        "events": dict(events),
    }
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


# ---- the dashboard ----


def _reported_counts(db: Session, since: datetime) -> dict[str, dict[tuple[str, str], int]]:
    rows = db.execute(
        select(ProductEvent.product, ProductEvent.kind, ProductEvent.name, func.count())
        .where(ProductEvent.occurred_at >= since)
        .group_by(ProductEvent.product, ProductEvent.kind, ProductEvent.name)
    ).all()
    out: dict[str, dict[tuple[str, str], int]] = {}
    for product, kind, name, count in rows:
        out.setdefault(product, {})[(kind, name)] = count
    return out


def recent(db: Session, *, limit: int = RECENT_LIMIT) -> list[dict]:
    """The latest signups and logins across every product, newest first."""
    rows = db.scalars(
        select(ProductEvent)
        .where(ProductEvent.kind.in_((SIGNUP, LOGIN)))
        .order_by(ProductEvent.occurred_at.desc(), ProductEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "product": r.product,
            "product_name": product_catalog.BY_KEY[r.product].name
            if r.product in product_catalog.BY_KEY
            else r.product,
            "kind": r.kind,
            "actor": r.actor,
            "occurred_at": as_aware(r.occurred_at),
        }
        for r in rows
    ]


def dashboard(
    db: Session, *, days: int, force: bool = False, client: UmamiClient | None = None
) -> dict:
    """The products dashboard: reported signups and events plus Umami traffic,
    per product, over ``days``."""
    client = client or get_client()
    since = utcnow() - timedelta(days=days)
    reported = _reported_counts(db, since)

    umami_error: str | None = None
    umami: dict[str, dict[str, Any]]
    if not client.configured:
        umami_error = "Umami is not configured (set UMAMI_USERNAME and UMAMI_PASSWORD)."
        umami = {p.key: {"status": "unconfigured"} for p in PRODUCTS}
    else:
        if force:
            clear_cache()
        try:
            sites = _site_ids(client)
        except UmamiError as exc:
            sites = {}
            umami_error = str(exc)
        with ThreadPoolExecutor(max_workers=min(8, len(PRODUCTS))) as pool:
            futures = {
                p.key: pool.submit(
                    _umami_for, client, p, resolve_website_id(p, sites), days, force=force
                )
                for p in PRODUCTS
            }
            umami = {key: f.result() for key, f in futures.items()}

    products = []
    totals: dict[str, int] = {"pageviews": 0, "visitors": 0, "active_now": 0, "signups": 0, "logins": 0}
    for p in PRODUCTS:
        u = umami[p.key]
        events = u.get("events", {})
        own = reported.get(p.key, {})

        def from_umami(names: Iterable[str], events: dict = events) -> int:
            return sum(events.get(n, 0) for n in names)

        def from_reports(kind: str, names: Iterable[str], own: dict = own) -> int:
            return sum(own.get((kind, n), 0) for n in names)

        signups = own.get((SIGNUP, SIGNUP), 0) + from_umami(SIGNUP_EVENTS)
        logins = own.get((LOGIN, LOGIN), 0) + from_umami(LOGIN_EVENTS)
        key_actions = [
            {
                "label": a.label,
                "events": list(a.events),
                "count": from_umami(a.events) + from_reports(ACTION, a.events),
            }
            for a in p.key_actions
        ]
        card = {
            "key": p.key,
            "name": p.name,
            "domain": p.domain,
            "url": p.url,
            "umami": {k: v for k, v in u.items() if k != "events"},
            "signups": signups,
            "logins": logins,
            "key_actions": key_actions,
            "reported_events": sum(own.values()),
        }
        products.append(card)
        if u.get("status") == "ok":
            totals["pageviews"] += u.get("pageviews", 0)
            totals["visitors"] += u.get("visitors", 0)
            totals["active_now"] += u.get("active_now", 0)
        totals["signups"] += signups
        totals["logins"] += logins

    return {
        "days": days,
        "generated_at": utcnow(),
        "umami_configured": client.configured,
        "umami_error": umami_error,
        "totals": totals,
        "products": products,
        "recent": recent(db),
    }
