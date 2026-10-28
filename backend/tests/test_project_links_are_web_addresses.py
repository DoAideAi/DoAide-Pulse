"""``repo_url`` and ``live_url`` are http(s) links or nothing.

They are the link every published post points a reader at and the ``<link>`` of
the project's public RSS feed, and they used to take any string — a
``javascript:`` URL included — while the import path already kept to http(s).
"""
from __future__ import annotations

import pytest

API = "/api/v1/projects"


def _create(client, auth, **fields):
    return client.post(API, headers=auth, json={"name": "Tidewatch", **fields})


@pytest.mark.parametrize(
    "field,value",
    [
        ("live_url", "javascript:alert(document.cookie)"),
        ("live_url", "JavaScript:alert(1)"),
        ("repo_url", "data:text/html,<script>alert(1)</script>"),
        ("live_url", "ftp://example.com/file"),
        ("live_url", "not a url"),
    ],
)
def test_a_non_web_address_is_refused_on_create(client, auth, field, value):
    response = _create(client, auth, **{field: value})

    assert response.status_code == 422, response.text


def test_a_non_web_address_is_refused_on_update(client, auth):
    project = _create(client, auth, live_url="https://tidewatch.example").json()

    response = client.patch(
        f"{API}/{project['id']}", headers=auth, json={"live_url": "javascript:alert(1)"}
    )

    assert response.status_code == 422, response.text
    assert client.get(f"{API}/{project['id']}", headers=auth).json()["live_url"] == (
        "https://tidewatch.example"
    )


def test_a_bare_host_gains_https_and_blank_means_none(client, auth):
    body = _create(client, auth, repo_url="github.com/acme/tidewatch", live_url="   ").json()

    assert body["repo_url"] == "https://github.com/acme/tidewatch"
    assert body["live_url"] is None


def test_web_addresses_are_kept_as_given(client, auth):
    body = _create(
        client, auth, repo_url="https://github.com/acme/tidewatch", live_url="http://tide.example/app"
    ).json()

    assert body["repo_url"] == "https://github.com/acme/tidewatch"
    assert body["live_url"] == "http://tide.example/app"
