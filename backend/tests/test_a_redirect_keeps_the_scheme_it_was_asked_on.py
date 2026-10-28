"""A trailing-slash redirect stays on HTTPS.

Caddy terminates TLS and forwards plain HTTP from the bridge address, which
uvicorn does not trust for ``X-Forwarded-Proto``, so every request reached the
app as ``http`` and ``GET /api/v1/projects/`` was answered with a ``307`` to
``http://pulse.doaide.com/api/v1/projects``. A client that follows it repeats
the request — bearer token, or a login form with the password — in clear text.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/api/v1/projects/"), ("POST", "/api/v1/auth/login/")],
)
def test_the_redirect_is_to_https_when_the_proxy_says_so(client, method, path):
    resp = client.request(
        method, path, headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
    )

    assert resp.status_code == 307
    assert resp.headers["location"].startswith("https://")


def test_without_the_header_nothing_changes(client):
    resp = client.get("/api/v1/projects/", follow_redirects=False)

    assert resp.headers["location"].startswith("http://")


def test_a_value_that_is_not_a_scheme_is_ignored(client):
    resp = client.get(
        "/api/v1/projects/",
        headers={"X-Forwarded-Proto": "javascript"},
        follow_redirects=False,
    )

    assert resp.headers["location"].startswith("http://")


def test_hsts_still_follows_the_forwarded_scheme(client):
    resp = client.get("/api/v1/health", headers={"X-Forwarded-Proto": "https"})

    assert "max-age" in resp.headers.get("strict-transport-security", "")
