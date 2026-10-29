"""The editor's sidebar listings check ownership without reading the article.

``GET /content/{id}/revisions`` and ``GET /content/{id}/preview-links`` need
the piece's id and nothing else, but both proved ownership with
``db.get(Content, id)``: the whole row, its body of up to 200,000 characters
included, then the ``lazy="selectin"`` publications, then the project to read
its owner — three queries and the body, on every sidebar open, before the
listing's own query ran.

They now ask one question, the id joined to its owner, and read nothing else
of the piece. The 404 for somebody else's piece is unchanged.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, status=ContentStatus.DRAFT,
        title="Long one", slug="long-one", body_markdown="word " * 20000,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.mark.parametrize("suffix", ["revisions", "preview-links"])
def test_the_listing_never_reads_the_body(client, auth, db, piece, sql_log, suffix):
    piece_id = piece.id  # read before expiring, or the test reloads the row itself
    db.expire_all()
    sql_log.clear()

    resp = client.get(f"/api/v1/content/{piece_id}/{suffix}", headers=auth)

    assert resp.status_code == 200, resp.text
    reads = [s for s in sql_log if s.startswith("SELECT")]
    assert not any("body_markdown" in s for s in reads), reads
    assert not any("FROM publications" in s for s in reads), reads


@pytest.mark.parametrize("suffix", ["revisions", "preview-links"])
def test_somebody_else_s_piece_is_still_a_404(client, db, piece, suffix):
    from app.models.user import User
    from app.security import hash_password

    other = User(email="other@example.com", hashed_password=hash_password("other-pass-123"))
    db.add(other)
    db.commit()
    login = client.post(
        "/api/v1/auth/login", data={"username": other.email, "password": "other-pass-123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/v1/content/{piece.id}/{suffix}", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Content not found."
