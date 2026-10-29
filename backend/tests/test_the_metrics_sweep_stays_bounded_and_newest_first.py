"""The metrics sweep stops polling old posts, and reaches new ones first.

``collect_all_metrics`` polled every post ever published, every six hours, for
the life of the install, and wrote a ``ContentMetric`` row each time. Nothing
deleted those rows and nothing ended the polling, so the table and the
outbound requests both grew with every post — four rows a day for a post from
three years ago whose numbers have not moved since.

And it walked them oldest first under a five-minute soft limit, restarting at
the lowest id on every run. Once there were more posts than one run could
reach, every run timed out on the old ones and the newest — whose first day and
second day are what the velocity windows and the underperformance alert are
measured on — were never polled at all.

Posts older than ``metrics_poll_max_age_days`` are now left alone, and the
rest are walked newest first.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform, Publication, PublicationStatus
from app.tasks import metrics_tasks


@pytest.fixture
def sweep(db, monkeypatch):
    class NoCloseProxy:
        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(metrics_tasks, "SessionLocal", NoCloseProxy)
    seen: list[str] = []

    def record(db_, publication, *, user_id=None, rate_limited=None, **kwargs):
        seen.append(publication.external_id)
        return None

    monkeypatch.setattr(metrics_tasks.publishing_service, "collect_metrics", record)
    return seen


def _published(db, project, external_id: str, *, days_ago: float) -> Publication:
    content = Content(
        project_id=project.id,
        title=external_id,
        slug=external_id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.PUBLISHED,
        body_markdown="body",
    )
    db.add(content)
    db.commit()
    row = Publication(
        content_id=content.id,
        platform=Platform.DEVTO,
        status=PublicationStatus.PUBLISHED,
        published_at=utcnow() - timedelta(days=days_ago),
        external_id=external_id,
    )
    db.add(row)
    db.commit()
    return row


def test_a_post_past_the_age_limit_is_no_longer_polled(db, project, user, sweep):
    _published(db, project, "ancient", days_ago=settings.metrics_poll_max_age_days + 1)
    _published(db, project, "recent", days_ago=2)

    metrics_tasks.collect_all_metrics()

    assert sweep == ["recent"]


def test_the_newest_posts_are_polled_first(db, project, user, sweep):
    # Inserted newest-published first, so id order and publish order disagree.
    _published(db, project, "yesterday", days_ago=1)
    _published(db, project, "last-week", days_ago=7)
    _published(db, project, "last-month", days_ago=30)

    metrics_tasks.collect_all_metrics()

    assert sweep == ["yesterday", "last-week", "last-month"]


def test_a_sweep_that_runs_out_of_time_has_reached_the_newest(
    db, project, user, sweep, monkeypatch
):
    for n in range(5):
        _published(db, project, f"old-{n}", days_ago=40 + n)
    _published(db, project, "brand-new", days_ago=0.5)

    real = metrics_tasks.publishing_service.collect_metrics

    def one_then_out_of_time(db_, publication, **kwargs):
        if sweep:
            raise SoftTimeLimitExceeded()
        return real(db_, publication, **kwargs)

    monkeypatch.setattr(metrics_tasks.publishing_service, "collect_metrics", one_then_out_of_time)

    metrics_tasks.collect_all_metrics()

    assert sweep == ["brand-new"]


def test_the_age_limit_is_a_validated_setting():
    assert settings.metrics_poll_max_age_days >= 1
