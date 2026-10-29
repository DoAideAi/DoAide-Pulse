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


def test_a_generated_piece_keeps_none_of_it(db, project):
    """Autopilot's pieces reach the row without a request schema in between."""
    from app.models.content import ContentStatus, ContentType
    from app.services.content_generator import GeneratedContent, content_from_generated

    generated = GeneratedContent(
        title="Release" + SNEAKY,
        body_markdown="Body. " * 40,
        excerpt=SNEAKY,
        meta_description=SNEAKY,
    )

    row = content_from_generated(
        db,
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        generated=generated,
        status=ContentStatus.REVIEW,
        source={},
    )

    assert row.title == "Release" + CLEAN
    assert row.excerpt == CLEAN
    assert row.meta_description == CLEAN


def test_a_generated_title_of_nothing_visible_still_has_a_title(db, project):
    from app.models.content import ContentStatus, ContentType
    from app.services.content_generator import GeneratedContent, content_from_generated

    generated = GeneratedContent(
        title="​‮", body_markdown="Body. " * 40, excerpt="", meta_description=""
    )

    row = content_from_generated(
        db,
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        generated=generated,
        status=ContentStatus.REVIEW,
        source={},
    )

    assert row.title == "Untitled"
    assert row.slug


def test_a_translation_keeps_none_of_it(client, auth, db, project, monkeypatch):
    """Translated one-line fields come from a model too, and go to platforms."""
    from app.models.content import Content, ContentStatus, ContentType
    from app.services import ai, llm_router

    piece = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.DRAFT,
        title="Retries",
        slug="retries",
        body_markdown="How retries work in practice, explained step by step. " * 10,
    )
    db.add(piece)
    db.commit()
    monkeypatch.setattr(
        ai,
        "json_completion",
        lambda *_a, **_k: (
            {
                "title": "Les" + SNEAKY,
                "body_markdown": "Comment fonctionnent les relances, étape par étape. " * 10,
                "excerpt": SNEAKY,
                "meta_description": SNEAKY,
            },
            llm_router.Completion(text="", provider="stub", model="stub"),
        ),
    )

    resp = client.post(
        f"/api/v1/content/{piece.id}/translations", headers=auth, json={"language": "fr"}
    )
    assert resp.status_code == 201, resp.text
    detail = client.get(f"/api/v1/content/{piece.id}/translations/fr", headers=auth).json()

    assert detail["title"] == "Les" + CLEAN
    assert detail["excerpt"] == CLEAN
    assert detail["meta_description"] == CLEAN
