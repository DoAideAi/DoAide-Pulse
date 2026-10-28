"""Project names and titles cannot be invisible or display as something else.

C104 M1. ``str.strip()`` let a zero-width space pass as a name, and kept a
right-to-left override that reverses how the text after it is drawn; and the
slug of an accented title lost every accented letter ("Ünïcödé" → ``n-c-d``).
"""
from __future__ import annotations

import pytest

from app.models.project import slugify
from app.schemas.text import visible_label

INVISIBLE = ["​", "​ ​", "﻿", "⁠", "­", "‮", "‍"]


@pytest.mark.parametrize("name", INVISIBLE)
def test_a_project_name_with_nothing_visible_is_refused(client, auth, name):
    resp = client.post("/api/v1/projects", json={"name": name, "description": "d"}, headers=auth)
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("title", INVISIBLE)
def test_a_title_with_nothing_visible_is_refused(client, auth, project, title):
    resp = client.post(
        "/api/v1/content",
        json={"project_id": project.id, "content_type": "tutorial", "title": title},
        headers=auth,
    )
    assert resp.status_code == 422, resp.text
    assert "invisible" in str(resp.json()["detail"])


def test_renaming_to_nothing_visible_is_refused_too(client, auth, project):
    resp = client.patch(f"/api/v1/projects/{project.id}", json={"name": "​"}, headers=auth)
    assert resp.status_code == 422, resp.text


def test_a_direction_override_is_removed_not_stored(client, auth, project):
    resp = client.post(
        "/api/v1/content",
        json={"project_id": project.id, "content_type": "tutorial", "title": "Invoice ‮fdp.exe"},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == "Invoice fdp.exe"


@pytest.mark.parametrize(
    "text",
    [
        "👨‍👩‍👧 Family plan",  # an emoji sequence held together by ZWJ
        "می‌خواهم",  # Persian: the ZWNJ is part of the spelling
        "🚀 Launch",
        "日本語プロジェクト",
    ],
)
def test_real_text_survives_intact(text):
    assert visible_label(text) == text


def test_surrounding_invisibles_are_trimmed_and_the_rest_kept():
    assert visible_label("​  Pulse​ ") == "Pulse"


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Ünïcödé Ünïcödé", "unicode-unicode"),
        ("Café crème", "cafe-creme"),
        ("é", "e"),
        ("Ｆｕｌｌｗｉｄｔｈ", "fullwidth"),
        ("日本語", "untitled"),
        ("🚀 Launch", "launch"),
    ],
)
def test_a_slug_keeps_the_base_letter_of_an_accented_one(title, slug):
    assert slugify(title) == slug
