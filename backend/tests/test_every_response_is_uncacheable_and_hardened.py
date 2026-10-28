"""Every response carries the caching and security headers — a census (C104 M4).

``SecurityHeadersMiddleware`` sets ``Cache-Control: no-store`` and the security
headers on whatever comes back through the stack, and a route may opt out of
``no-store`` only by setting its own ``Cache-Control``. Nothing enforced either
half per route: a route could set a cacheable header on account data and the
middleware would let it through, and a shared cache in front (Cloudflare) would
then hand one account's numbers to another.

So every GET route is called — signed in and signed out, with any path
parameter filled with an id that does not exist, so errors are swept as well as
successes — and every answer is checked. The opt-outs are listed here, by name,
with the reason. The catch-all 500 is checked separately: Starlette serves it
from outside every middleware, and it carried none of these headers.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, create_app

#: Routes allowed their own ``Cache-Control``, and why.
CACHEABLE = {
    # An uploaded image: public by URL, content-addressed, never changes.
    "/api/v1/uploads/{filename}": "public, max-age=31536000, immutable",
}

HARDENED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}

_PARAM = re.compile(r"\{([^}:]+)(:[^}]+)?\}")


def _get_routes() -> list[str]:
    """Every GET path, prefix included, as the published schema lists it."""
    return sorted(path for path, ops in app.openapi()["paths"].items() if "get" in ops)


def _fill(path: str) -> str:
    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if "language" in name:
            return "fr"
        if name in ("platform",):
            return "devto"
        if name in ("slug", "filename", "token", "key", "site_key", "product"):
            return "does-not-exist"
        return "999999"

    return _PARAM.sub(value, path)


def test_the_walk_finds_the_api():
    paths = _get_routes()
    assert len(paths) > 60
    assert "/api/v1/content/{content_id}" in paths


@pytest.mark.parametrize("signed_in", [True, False], ids=["signed-in", "anonymous"])
@pytest.mark.parametrize("path", _get_routes())
def test_every_get_answer_is_hardened(client, auth, path, signed_in):
    resp = client.get(_fill(path), headers=auth if signed_in else {})

    for header, expected in HARDENED.items():
        assert resp.headers.get(header) == expected, (path, resp.status_code, header)
    assert "content-security-policy" in resp.headers, (path, resp.status_code)

    cache = resp.headers.get("cache-control")
    if path in CACHEABLE and resp.status_code == 200:
        assert cache == CACHEABLE[path]
    else:
        assert cache == "no-store", (path, resp.status_code, cache)


def test_the_cacheable_list_names_only_real_routes():
    assert set(CACHEABLE) <= set(_get_routes())


@pytest.mark.parametrize("environment", ["production", "development"])
def test_the_catch_all_500_is_hardened_too(monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "debug", False)
    fresh = create_app()

    @fresh.get("/__boom")
    async def _boom():
        raise RuntimeError("boom")

    with TestClient(fresh, raise_server_exceptions=False) as client:
        resp = client.get("/__boom")

    assert resp.status_code == 500
    assert resp.headers.get("cache-control") == "no-store"
    for header, expected in HARDENED.items():
        assert resp.headers.get(header) == expected, header
    assert "content-security-policy" in resp.headers
    assert resp.headers.get("x-request-id")
    assert "boom" not in resp.text
