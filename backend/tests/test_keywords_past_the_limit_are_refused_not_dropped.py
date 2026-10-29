"""A ninth keyword is refused with the limit, not silently thrown away.

``ContentCreate``/``ContentUpdate`` accepted up to 30 keywords, and the router
then passed them through ``seo.normalize_keywords``, which keeps the first
``KEYWORD_MAX`` (8). A person who saved twelve keywords got a 200 and a piece
with eight: four gone, with nothing anywhere saying so, and the editor's next
load showing fewer than were typed.

The schema's bound is now ``KEYWORD_MAX`` itself, so the request that would
lose some is a 422 naming the limit, and everything at or under it is kept as
before (lowercased and de-duplicated, as it always was).
"""
from __future__ import annotations

from app.schemas.content import ContentCreate, ContentUpdate
from app.services import seo

API = "/api/v1/content"


def _body(project, keywords):
    return {
        "project_id": project.id,
        "content_type": "announcement",
        "title": "Shipping",
        "body_markdown": "Body.",
        "keywords": keywords,
    }


def test_the_schemas_allow_exactly_what_is_kept():
    for model in (ContentCreate, ContentUpdate):
        bound = next(
            m.max_length for m in model.model_fields["keywords"].metadata
            if getattr(m, "max_length", None)
        )
        assert bound == seo.KEYWORD_MAX


def test_more_keywords_than_are_kept_is_a_422_on_create(client, auth, project):
    words = [f"keyword{n}" for n in range(seo.KEYWORD_MAX + 1)]

    resp = client.post(API, headers=auth, json=_body(project, words))

    assert resp.status_code == 422, resp.text


def test_and_on_edit_and_nothing_is_lost(client, auth, project):
    piece = client.post(API, headers=auth, json=_body(project, ["one"])).json()
    words = [f"keyword{n}" for n in range(seo.KEYWORD_MAX + 4)]

    resp = client.patch(f"{API}/{piece['id']}", headers=auth, json={"keywords": words})

    assert resp.status_code == 422, resp.text
    assert client.get(f"{API}/{piece['id']}", headers=auth).json()["keywords"] == ["one"]


def test_up_to_the_limit_is_kept_whole(client, auth, project):
    words = [f"keyword{n}" for n in range(seo.KEYWORD_MAX)]

    resp = client.post(API, headers=auth, json=_body(project, words))

    assert resp.status_code == 201, resp.text
    assert resp.json()["keywords"] == words
