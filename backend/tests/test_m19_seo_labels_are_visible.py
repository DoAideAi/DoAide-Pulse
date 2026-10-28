"""M19: a tag, keyword or focus keyword has to be something a reader can see.

Titles and project names already went through ``visible_label``. The three
SEO label fields next to them used ``strip``, which leaves zero-width spaces
and bidi overrides alone — and ``focus_keyword`` was not even stripped, so
``"   "`` became the keyword every SEO check searched the piece for.
"""
from __future__ import annotations

import pytest

from app.models.content import Content
from app.services.seo import normalize_keywords

INVISIBLE = ["   ", "​", "‮​ ", "﻿⁠"]


def _create(client, auth, project, **fields):
    resp = client.post(
        "/api/v1/content",
        json={"project_id": project.id, "title": "A title", "body_markdown": "Body.", **fields},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize("value", INVISIBLE)
def test_an_invisible_tag_keyword_or_focus_keyword_is_dropped(client, auth, db, project, value):
    cid = _create(
        client, auth, project,
        tags=[value, "release"], keywords=[value, "deploy"], focus_keyword=value,
    )
    piece = db.get(Content, cid)
    assert piece.tags == ["release"]
    assert piece.keywords == ["deploy"]
    # Not the invisible value; derived from the first real keyword instead.
    assert piece.focus_keyword == "deploy"


def test_a_whitespace_focus_keyword_on_update_clears_it(client, auth, db, project):
    cid = _create(client, auth, project, focus_keyword="deploy pipelines")
    resp = client.patch(f"/api/v1/content/{cid}", json={"focus_keyword": "  ​ "}, headers=auth)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(Content, cid).focus_keyword == ""


def test_real_labels_keep_their_text(client, auth, db, project):
    cid = _create(
        client, auth, project,
        tags=["  Guides/Docker  ", "नमस्ते"],
        keywords=["Zero  Downtime", "كلمة"],
        focus_keyword="  zero   downtime ",
    )
    piece = db.get(Content, cid)
    assert piece.tags == ["Guides/Docker", "नमस्ते"]
    assert piece.keywords == ["zero downtime", "كلمة"]
    assert piece.focus_keyword == "zero downtime"


def test_normalize_keywords_drops_what_cannot_be_seen():
    assert normalize_keywords(["‮​", "​​", "real one"]) == ["real one"]
