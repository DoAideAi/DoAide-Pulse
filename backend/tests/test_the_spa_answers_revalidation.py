"""``no-cache`` means "check first", and the SPA server gave nothing to check.

Everything outside ``/assets`` goes out as ``Cache-Control: no-cache`` — keep
it, but revalidate before using it — so that a deploy reaches every client on
its next load. Revalidating needs a validator, and ``static-server.mjs`` sent
neither an ``ETag`` nor a ``Last-Modified`` and never answered 304. So
``no-cache`` behaved as no caching at all: every navigation downloaded the
whole shell (and every prerendered page, ``sw.js``, the manifest, the icons)
again, to find it was the same bytes as last time.

The server now tags each file from its size and modification time, and a
matching ``If-None-Match`` (or an ``If-Modified-Since`` at or after the file's
time) gets a 304 with no body. A deploy rewrites the files, so their tags
change and the next load fetches the new ones — the guarantee ``no-cache`` was
there for is kept.

Runs the real server, with the fixtures of the CSP test beside it.
"""
from __future__ import annotations

import os
import time

import httpx

from tests.test_the_spa_is_served_with_a_policy import base_url, root  # noqa: F401


def test_the_shell_carries_validators(base_url):  # noqa: F811
    resp = httpx.get(f"{base_url}/")

    assert resp.status_code == 200
    assert resp.headers.get("etag")
    assert resp.headers.get("last-modified")
    assert resp.headers["cache-control"] == "no-cache"


def test_a_matching_etag_is_answered_with_304_and_no_body(base_url):  # noqa: F811
    first = httpx.get(f"{base_url}/index.html")

    again = httpx.get(f"{base_url}/index.html", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == first.headers["etag"]
    # Still the policy and the caching rule: a 304 updates the stored headers.
    assert again.headers["cache-control"] == "no-cache"
    assert "content-security-policy" in again.headers


def test_the_spa_fallback_revalidates_too(base_url):  # noqa: F811
    """Every real page load is a route the fallback serves, not /index.html."""
    first = httpx.get(f"{base_url}/content/42")

    again = httpx.get(f"{base_url}/content/42", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304


def test_if_modified_since_is_honoured(base_url):  # noqa: F811
    first = httpx.get(f"{base_url}/index.html")

    again = httpx.get(
        f"{base_url}/index.html", headers={"If-Modified-Since": first.headers["last-modified"]}
    )

    assert again.status_code == 304


def test_a_stale_tag_gets_the_file(base_url):  # noqa: F811
    resp = httpx.get(f"{base_url}/index.html", headers={"If-None-Match": '"not-the-tag"'})

    assert resp.status_code == 200
    assert b"Pulse" in resp.content


def test_a_deploy_changes_the_tag(base_url, root):  # noqa: F811
    before = httpx.get(f"{base_url}/index.html").headers["etag"]
    page = root / "index.html"
    page.write_text("<!doctype html><title>Pulse, next deploy</title>", "utf-8")
    later = time.time() + 5
    os.utime(page, (later, later))

    after = httpx.get(f"{base_url}/index.html", headers={"If-None-Match": before})

    assert after.status_code == 200
    assert after.headers["etag"] != before
    assert b"next deploy" in after.content
