"""A JSON body carrying ``\\u0000`` is refused at the door, not at the write.

PostgreSQL keeps no NUL in ``text`` or ``jsonb``; psycopg raises ``DataError``
when one reaches a write, and that fell through to the catch-all as a 500 —
"something failed inside Pulse" for a title the caller could simply fix.
SQLite stores NUL happily, so the suite never saw it. The body scanner that
already walks every JSON request for nesting depth now notices the escape too.
"""
from __future__ import annotations

import pytest

from app.main import _JSONDepthScanner


def _scan(*chunks: bytes) -> bool:
    scanner = _JSONDepthScanner()
    for chunk in chunks:
        scanner.feed(chunk)
    return scanner.has_nul


@pytest.mark.parametrize(
    "body",
    [
        b'{"title": "a\\u0000b"}',
        b'["\\u0000"]',
        b'{"\\u0000": 1}',
    ],
)
def test_a_nul_escape_in_a_string_is_noticed(body):
    assert _scan(body)


@pytest.mark.parametrize(
    "body",
    [
        b'{"title": "a\\u0001b"}',
        b'{"title": "a\\u00e9b"}',
        # An escaped backslash followed by the letters: text, not an escape.
        b'{"title": "a\\\\u0000b"}',
        b'{"title": "u0000"}',
    ],
)
def test_lookalikes_are_not(body):
    assert not _scan(body)


def test_an_escape_split_across_chunks_is_still_noticed():
    body = b'{"t": "x\\u0000"}'
    for cut in range(1, len(body)):
        assert _scan(body[:cut], body[cut:]), cut


def test_the_api_answers_400_rather_than_reaching_the_database(client, auth, project):
    resp = client.post(
        "/api/v1/content",
        headers={**auth, "Content-Type": "application/json"},
        content=(
            '{"project_id": %d, "content_type": "announcement", '
            '"title": "Launch\\u0000", "body_markdown": "Body"}' % project.id
        ),
    )
    assert resp.status_code == 400, resp.text
    assert "NUL" in resp.json()["detail"]


def test_an_ordinary_body_is_untouched(client, auth, project):
    resp = client.post(
        "/api/v1/content",
        headers=auth,
        json={
            "project_id": project.id,
            "content_type": "announcement",
            "title": "Café é launch",
            "body_markdown": "Body",
        },
    )
    assert resp.status_code == 201, resp.text
