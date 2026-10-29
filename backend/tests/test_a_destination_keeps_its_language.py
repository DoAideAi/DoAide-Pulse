"""A destination's language is stored when it is set, and kept when it is not.

``ConnectionCreate`` declared and validated ``language``; nothing wrote it to
the row. Every destination stayed English, the publish path's translation
lookup read a column no request could set, and publishing a piece in French
was not something a user could do.
"""
from __future__ import annotations

import httpx
import pytest

from app.models.platform_connection import PlatformConnection
from app.services.publishers import base

URL = "/api/v1/settings/connections"


@pytest.fixture(autouse=True)
def buttondown(monkeypatch):
    monkeypatch.setattr(
        base,
        "_exchange",
        lambda method, url, **_k: httpx.Response(
            200, json={"username": "x"}, request=httpx.Request(method, url)
        ),
    )


def _save(client, auth, **extra):
    body = {"platform": "buttondown", "credentials": {"api_key": "bd"}, **extra}
    resp = client.put(URL, headers=auth, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_the_language_is_stored(client, auth, db):
    assert _save(client, auth, language="fr")["language"] == "fr"
    assert db.query(PlatformConnection).one().language == "fr"


def test_resaving_the_key_without_a_language_keeps_it(client, auth, db):
    _save(client, auth, language="de")
    assert _save(client, auth)["language"] == "de"


def test_a_regional_tag_is_stored_as_its_base(client, auth):
    assert _save(client, auth, language="fr-CA")["language"] == "fr"


def test_a_language_the_translator_cannot_produce_is_refused(client, auth):
    resp = client.put(
        URL,
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd"}, "language": "xx"},
    )
    assert resp.status_code == 422
