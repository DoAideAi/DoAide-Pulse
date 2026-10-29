"""The metrics sweep's page query walks ``publications.published_at``'s index.

M5 made the sweep go newest first by ordering on
``coalesce(published_at, created_at)``. No index covers that expression, so
every page — two hundred rows at a time, for as many pages as the install has
posts — sorted every published row from scratch, where the keyset on ``id`` it
replaced walked the primary key. The coalesce bought nothing: the one path that
marks a publication published writes ``published_at`` in the same statement,
and the column has been in the schema since the first migration, indexed.

So the page filters and orders on ``published_at`` itself, which that index
can serve in order instead of sorting the set on every page.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.tasks import metrics_tasks


@pytest.fixture
def page_queries(db, project, user, sql_log, monkeypatch):
    class NoCloseProxy:
        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(metrics_tasks, "SessionLocal", NoCloseProxy)
    monkeypatch.setattr(
        metrics_tasks.publishing_service, "collect_metrics", lambda *a, **k: None
    )
    content = Content(
        project_id=project.id, title="Live", slug="live",
        content_type=ContentType.ANNOUNCEMENT, status=ContentStatus.PUBLISHED, body_markdown="b",
    )
    db.add(content)
    db.commit()
    db.add(
        Publication(
            content_id=content.id, platform=Platform.DEVTO, status=PublicationStatus.PUBLISHED,
            published_at=utcnow(), external_id="x",
        )
    )
    db.commit()
    sql_log.clear()
    metrics_tasks.collect_all_metrics()
    return [s for s in sql_log if s.startswith("SELECT") and "FROM publications" in s]


def test_the_page_query_names_the_column_not_an_expression(page_queries):
    assert page_queries, "the sweep issued no page query"
    for statement in page_queries:
        assert "coalesce" not in statement.lower()
        assert "publications.published_at >=" in statement


def test_it_orders_on_columns_an_index_can_serve(page_queries):
    assert (
        "ORDER BY publications.published_at DESC, publications.id DESC" in page_queries[0]
    )


def test_published_at_is_indexed():
    """The index that order walks (and the trailing id is the index's own rowid)."""
    indexed = {
        tuple(column.name for column in index.columns)
        for index in Publication.__table__.indexes
    }
    assert ("published_at",) in indexed
