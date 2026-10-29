"""A count a platform reports is stored as a count, or not at all.

The adapters pass the platform's JSON numbers straight through. One that is
negative trips ``ck_metric_views_nonneg`` at the sweep's batch commit, which
rolls back every other publication's reading in the batch with it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.content import Content, ContentStatus, ContentType
from app.models.metrics import ContentMetric
from app.models.mixins import utcnow
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishers, publishing_service
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import MetricsSnapshot


@pytest.fixture
def connected(db, user):
    db.add(
        PlatformConnection(
            user_id=user.id,
            platform=Platform.DEVTO,
            status=ConnectionStatus.CONNECTED,
            encrypted_credentials=encrypt_credentials({"api_key": "k"}),
        )
    )
    db.commit()


def _published(db, project, external_id: str) -> Publication:
    content = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.PUBLISHED,
        title=f"Post {external_id}",
        slug=f"post-{external_id}",
        body_markdown="Words.",
    )
    db.add(content)
    db.flush()
    publication = Publication(
        content_id=content.id,
        platform=Platform.DEVTO,
        status=PublicationStatus.PUBLISHED,
        external_id=external_id,
        # Published rows always carry it; the sweep pages on it.
        published_at=utcnow(),
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication


@pytest.mark.parametrize(
    ("raw", "stored"),
    [(-1, None), (True, None), ("12", 12), (" 7 ", 7), ("1.2k", None), (12.0, 12), (1.5, None), (0, 0)],
)
def test_a_reported_value_is_stored_only_as_a_count(raw, stored):
    assert publishing_service._count(raw) == stored


def test_one_negative_count_does_not_cost_the_batch(
    db, project, connected, monkeypatch
):
    from app.tasks import metrics_tasks

    snapshots = {"good": MetricsSnapshot(views=40), "bad": MetricsSnapshot(views=-1, reactions=3)}
    monkeypatch.setattr(
        publishers.get_adapter(Platform.DEVTO),
        "fetch_metrics",
        lambda external_id, credentials: snapshots[external_id],
    )
    good = _published(db, project, "good")
    bad = _published(db, project, "bad")

    class _Session:
        def __call__(self):
            return self

        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(metrics_tasks, "SessionLocal", _Session())
    metrics_tasks.collect_all_metrics()

    rows = {m.publication_id: m for m in db.scalars(select(ContentMetric))}
    assert rows[good.id].views == 40
    assert rows[bad.id].views is None
    assert rows[bad.id].reactions == 3


def test_a_dropped_value_is_logged_with_the_platform_and_field(
    db, project, connected, monkeypatch, caplog
):
    """Stored as "not reported", and said so — or a platform's format change
    would look exactly like a platform that does not report the number."""
    import logging

    from app.services import publishing_service

    monkeypatch.setattr(
        publishers.get_adapter(Platform.DEVTO),
        "fetch_metrics",
        lambda external_id, credentials: MetricsSnapshot(
            views=2**40, reactions="lots", comments=4
        ),
    )
    publication = _published(db, project, "odd")

    with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
        publishing_service.collect_metrics(db, publication)

    line = next(r.getMessage() for r in caplog.records if "not counts" in r.getMessage())
    assert f"publication {publication.id} on devto" in line
    assert "views=1099511627776" in line and "reactions='lots'" in line
    assert "comments" not in line


def test_a_clean_snapshot_logs_nothing(db, project, connected, monkeypatch, caplog):
    import logging

    from app.services import publishing_service

    monkeypatch.setattr(
        publishers.get_adapter(Platform.DEVTO),
        "fetch_metrics",
        lambda external_id, credentials: MetricsSnapshot(views=10, reactions=None),
    )
    publication = _published(db, project, "clean")

    with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
        publishing_service.collect_metrics(db, publication)

    assert "not counts" not in caplog.text
