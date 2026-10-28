"""A search term is text — never a pattern, never SQL, never one of two spellings
(C104 M6).

``GET /content?q=`` is an ``ILIKE`` underneath, where ``%``, ``_`` and ``\\`` mean
something, and it is the one place a user's free text meets a query directly.
Each term below matches exactly the titles that contain it as typed. And a
decomposed "é" (``e`` + U+0301, what macOS hands over from a file name) is the
same text as the precomposed one: titles are stored composed, and the term is
composed before it is compared.
"""
from __future__ import annotations

import pytest

TITLES = [
    "100% uptime", "snake_case names", "back\\slash", "O'Reilly guide",
    "plain title", "Ünïcödé café",
]


@pytest.fixture
def library(client, auth, project):
    for title in TITLES:
        resp = client.post(
            "/api/v1/content", headers=auth, json={"project_id": project.id, "title": title}
        )
        assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(
    ("term", "found"),
    [
        ("%", ["100% uptime"]),
        ("_", ["snake_case names"]),
        ("100%", ["100% uptime"]),
        ("\\", ["back\\slash"]),
        ("'", ["O'Reilly guide"]),
        ("'; DROP TABLE content; --", []),
        ('" OR 1=1 --', []),
        ("*", []),
        ("[a-z]", []),
        ("café", ["Ünïcödé café"]),
        ("café", ["Ünïcödé café"]),  # decomposed
        ("Ün", ["Ünïcödé café"]),  # decomposed, start of title
    ],
)
def test_a_term_matches_what_it_says(client, auth, library, term, found):
    resp = client.get("/api/v1/content", headers=auth, params={"q": term})
    assert resp.status_code == 200, resp.text
    assert sorted(c["title"] for c in resp.json()) == sorted(found)


def test_the_table_is_still_there(client, auth, library):
    client.get("/api/v1/content", headers=auth, params={"q": "'; DROP TABLE content; --"})
    assert len(client.get("/api/v1/content", headers=auth).json()) == len(TITLES)


def test_a_decomposed_title_is_stored_composed(client, auth, project):
    resp = client.post(
        "/api/v1/content", headers=auth, json={"project_id": project.id, "title": "Café notes"}
    )
    assert resp.json()["title"] == "Café notes"
    assert resp.json()["slug"] == "cafe-notes"
