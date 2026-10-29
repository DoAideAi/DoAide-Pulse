"""The excerpt, the meta description and an API key's name are cleaned like a title.

The title had ``visible_label`` — no control characters, no zero-width
characters, no reordering overrides — and the two lines published beside it
did not. A meta description carrying U+202E (RIGHT-TO-LEFT OVERRIDE) reverses
how the rest of the line renders in a search snippet or on Dev.to; a terminal
escape in an API key's name reaches the journal on every rotation.
"""
from __future__ import annotations

import pytest

SNEAKY = "Fast‮ retliF ​setup\x1b[2J\x07"
CLEAN = "Fast retliF setup[2J"


def test_a_new_piece_keeps_none_of_it(client, auth, project):
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "title": "A piece",
            "body_markdown": "Body. " * 40,
            "meta_description": SNEAKY,
            "excerpt": SNEAKY,
        },
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["meta_description"] == CLEAN
    assert resp.json()["excerpt"] == CLEAN


def test_an_edit_keeps_none_of_it(client, auth, project):
    piece = client.post(
        "/api/v1/content",
        headers=auth,
        json={"project_id": project.id, "title": "A piece", "body_markdown": "Body. " * 40},
    ).json()

    resp = client.patch(
        f"/api/v1/content/{piece['id']}", headers=auth, json={"meta_description": SNEAKY}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["meta_description"] == CLEAN


def test_a_key_name_keeps_none_of_it(client, auth, project):
    resp = client.post(
        "/api/v1/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": "ci" + SNEAKY, "scopes": ["content:read"]},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "ci" + CLEAN


@pytest.mark.parametrize("name", ["​", "‮", " \x07 "])
def test_a_key_name_of_nothing_visible_is_refused(client, auth, project, name):
    resp = client.post(
        "/api/v1/api-keys",
        headers=auth,
        json={"project_id": project.id, "name": name, "scopes": ["content:read"]},
    )

    assert resp.status_code == 422
