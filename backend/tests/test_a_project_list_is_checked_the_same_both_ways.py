"""A project's keywords and tech stack are checked the same on create and on edit.

The two models disagreed in both directions. ``ProjectCreate`` cleaned the
lists (trim, drop blanks, dedupe case-insensitively) but took items of any
length; ``ProjectUpdate`` capped each item but cleaned nothing. So a create
could store a keyword as long as the body limit, and a PATCH could store the
blanks and repeats a create would have removed.
"""
from __future__ import annotations

import pytest

from app.services.seo import KEYWORD_MAX_LENGTH


@pytest.mark.parametrize("field", ["keywords", "tech_stack"])
def test_creating_with_an_overlong_item_is_refused(client, auth, field):
    resp = client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Long", field: ["x" * (KEYWORD_MAX_LENGTH + 500)]},
    )

    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("field", ["keywords", "tech_stack"])
def test_editing_cleans_the_list_as_creating_does(client, auth, project, field):
    resp = client.patch(
        f"/api/v1/projects/{project.id}",
        headers=auth,
        json={field: ["", "  ", " FastAPI ", "fastapi", "React"]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()[field] == ["FastAPI", "React"]


def test_creating_still_cleans_the_list(client, auth):
    resp = client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Clean", "keywords": [" seo ", "SEO", "", "growth"]},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["keywords"] == ["seo", "growth"]
