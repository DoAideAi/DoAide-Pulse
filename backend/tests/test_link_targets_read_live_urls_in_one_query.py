"""An internal-link target's live URL is read in one query, not one per post.

``seo_autofix._link_targets`` looked up a publication URL for every
published post without a canonical URL — a SELECT per row, up to 200 of them
each time a draft's internal link count was taken — and with no ORDER BY, so
which platform's URL it got was arbitrary.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import seo_autofix


def _published(db, project, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        piece = Content(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            title=f"Post {i}",
            slug=f"post-{i}",
            status=ContentStatus.PUBLISHED,
            keywords=["fastapi"],
        )
        db.add(piece)
        db.flush()
        for platform in (Platform.DEVTO, Platform.HASHNODE):
            db.add(
                Publication(
                    content_id=piece.id,
                    platform=platform,
                    status=PublicationStatus.PUBLISHED,
                    external_url=f"https://{platform.value}.example.com/post-{i}",
                )
            )
    db.commit()


def _draft(db, project) -> Content:
    draft = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Draft",
        slug="draft",
        status=ContentStatus.DRAFT,
        keywords=["fastapi"],
    )
    db.add(draft)
    db.commit()
    return draft


def _selects(db, sql_log, draft, project) -> tuple[int, list]:
    db.expire_all()
    sql_log.clear()
    targets = seo_autofix._link_targets(db, draft, project)
    return len([s for s in sql_log if s.startswith("SELECT")]), targets


def test_the_query_count_does_not_grow_with_the_posts(db, project, sql_log):
    draft = _draft(db, project)
    _published(db, project, 3)
    few, _ = _selects(db, sql_log, draft, project)
    _published(db, project, 27, start=3)
    many, _ = _selects(db, sql_log, draft, project)
    assert few == many


def test_the_earliest_publication_is_the_url_used(db, project, sql_log):
    draft = _draft(db, project)
    _published(db, project, 1)
    _, targets = _selects(db, sql_log, draft, project)
    assert ("Post 0", "https://devto.example.com/post-0") in targets


def test_a_canonical_url_still_wins(db, project, sql_log):
    draft = _draft(db, project)
    _published(db, project, 1)
    piece = db.query(Content).filter_by(slug="post-0").one()
    piece.canonical_url = "https://blog.example.com/post-0"
    db.commit()
    _, targets = _selects(db, sql_log, draft, project)
    assert ("Post 0", "https://blog.example.com/post-0") in targets
