"""A NUL in the URL is a 400 at the door, like a NUL in a JSON body.

Path and query parameters reach SQL as readily as body fields —
``GET /articles/{slug}`` is ``WHERE slug = ?`` — and PostgreSQL refuses NUL
in a bound text parameter, so ``/articles/a%00`` was a 500 from an
unauthenticated route. SQLite accepts it, which is why the assertion here is
on the middleware's answer rather than on a database error.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/articles/hello%00world",
        "/api/v1/content?status=draft%00",
        "/api/v1/tags?project_id=1&q=%00",
    ],
)
def test_nul_in_the_path_or_query_is_400(client, url):
    resp = client.get(url)

    assert resp.status_code == 400, resp.text
    assert "NUL" in resp.json()["detail"]


def test_an_ordinary_url_is_untouched(client):
    resp = client.get("/api/v1/articles/caf%C3%A9-100%25")

    assert resp.status_code == 404, resp.text
