"""Every paged listing says how many there are — a census (C104 M4).

A listing that takes ``offset`` is one a client pages through, and the only way
it knows when to stop, or how many pages to draw, is the total before paging.
Pulse sends that in ``X-Total-Count`` on every such listing today, by
convention; this makes the convention a rule, so a new paged route that forgets
it fails here instead of in a client that pages for ever or stops at one.

Static rather than called: several of these sit under a resource id, and what
is being checked is the handler, not the data.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi.routing import APIRoute

from app.config import settings
from app.main import app


def _walk(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _walk(route.original_router.routes)
        elif hasattr(route, "routes"):
            yield from _walk(route.routes)


def _paged() -> list[tuple[str, APIRoute]]:
    # The walk sees the routers' own paths; the schema has them under the API
    # prefix the include adds.
    by_path = {
        settings.api_v1_prefix + route.path: route
        for route in _walk(app.routes)
        if "GET" in (route.methods or ())
    }
    found = []
    for path, ops in app.openapi()["paths"].items():
        op = ops.get("get")
        if op and any(p["name"] == "offset" for p in op.get("parameters", [])):
            found.append((path, by_path[path]))
    return sorted(found, key=lambda pair: pair[0])


PAGED = _paged()


def test_the_census_finds_the_paged_listings():
    paths = [path for path, _ in PAGED]
    assert len(paths) >= 14
    assert "/api/v1/content" in paths
    assert "/api/v1/webhooks/{webhook_id}/deliveries" in paths


@pytest.mark.parametrize(("path", "route"), PAGED, ids=[p for p, _ in PAGED])
def test_a_paged_listing_sets_its_total(path, route):
    source = inspect.getsource(route.endpoint)
    assert 'response.headers["X-Total-Count"]' in source, (
        f"{path} takes an offset but never sets X-Total-Count, so a client "
        "paging through it cannot tell when to stop."
    )


def test_the_total_is_readable_cross_origin():
    """A header the browser hides from the SPA is a header it does not have."""
    from starlette.middleware.cors import CORSMiddleware

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert "X-Total-Count" in cors.kwargs["expose_headers"]


def test_a_listing_with_rows_reports_them(client, auth, project):
    resp = client.get("/api/v1/projects", headers=auth, params={"limit": 1})
    assert resp.headers["X-Total-Count"] == "1"
