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


def test_the_language_is_in_the_connect_log_line(client, auth, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="app.routers.settings"):
        _save(client, auth, language="fr")

    assert "language=fr" in caplog.text


def test_both_language_refusals_point_at_a_route_that_answers(client, auth, project, db):
    """The translation refusal said "See GET /content/languages", a path that
    does not exist; the connection refusal said /languages. Both now name the
    real one, and it answers."""
    from app.models.content import Content, ContentType

    piece = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="T",
        slug="t",
        body_markdown="b",
    )
    db.add(piece)
    db.commit()
    translated = client.post(
        f"/api/v1/content/{piece.id}/translations", headers=auth, json={"language": "xx"}
    )
    connected = client.put(
        URL,
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd"}, "language": "xx"},
    )

    for resp in (translated, connected):
        assert resp.status_code == 422
        assert "See GET /languages." in resp.text
    assert client.get("/api/v1/languages", headers=auth).status_code == 200
