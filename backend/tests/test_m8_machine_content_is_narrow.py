"""M8: ``GET /machine/content`` reads the columns it returns, nothing more.

It selected whole ``Content`` entities: every article body on the page, plus a
``selectin`` load of every publication of every piece — for a response that
carries neither, and whose docstring promises a narrow SELECT.
"""
from __future__ import annotations

from app.models.api_key import ALL_SCOPES
from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import api_keys

V1 = "/api/v1"


def _seed(db, project, n: int) -> None:
    for i in range(n):
        piece = Content(
            project_id=project.id,
            content_type=ContentType.ANNOUNCEMENT,
            status=ContentStatus.PUBLISHED,
            title=f"Post {i}",
            slug=f"post-{i}",
            body_markdown="A long body. " * 200,
        )
        db.add(piece)
        db.flush()
        db.add(
            Publication(
                content_id=piece.id,
                platform=Platform.DEVTO,
                status=PublicationStatus.PUBLISHED,
            )
        )
    db.commit()


def test_the_machine_listing_reads_no_body_and_no_publications(
    client, db, project, sql_log
):
    _, token = api_keys.mint(db, project=project, name="CI", scopes=list(ALL_SCOPES))
    db.commit()
    _seed(db, project, 5)
    db.expire_all()
    sql_log.clear()

    resp = client.get(f"{V1}/machine/content?limit=50", headers={"X-API-Key": token})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 5
    assert body[0]["word_count"] > 0
    assert set(body[0]) >= {"id", "title", "slug", "content_type", "status", "word_count"}
    content_reads = [s for s in sql_log if s.startswith("SELECT") and "FROM content" in s]
    assert content_reads, sql_log
    assert not any("body_markdown" in s for s in content_reads), content_reads
    assert not any("FROM publications" in s for s in sql_log), sql_log
