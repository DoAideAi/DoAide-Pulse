"""M3: ``content.published`` fires once when two platforms land together.

The event means "a piece went live for the first time". ``execute`` decided
that from the piece as it loaded it, before the platform call. Two workers
publishing one piece to two platforms both loaded it unpublished; the second to
commit lost the content row's version check, and ``_commit_outcome`` re-applied
the outcome to the piece as the first worker left it — already published. The
stale verdict survived the reload and the second worker announced it again.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import PublishResult
from app.services.publishers.devto import DevToAdapter
from tests.conftest import TestSession


@pytest.fixture
def two_rows(db, user, project) -> tuple[Publication, Publication]:
    piece = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED,
        title="Pulse 2.0 is out",
        slug="pulse-2-0-is-out",
        body_markdown="# Pulse 2.0\n\nThe release is available today.\n",
    )
    db.add(piece)
    db.add(
        PlatformConnection(
            user_id=user.id,
            platform=Platform.DEVTO,
            status=ConnectionStatus.CONNECTED,
            encrypted_credentials=encrypt_credentials({"api_key": "k"}),
        )
    )
    db.commit()
    rows = (
        Publication(content_id=piece.id, platform=Platform.DEVTO, status=PublicationStatus.PENDING),
        Publication(content_id=piece.id, platform=Platform.MEDIUM, status=PublicationStatus.PUBLISHING),
    )
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _other_worker_lands_first(monkeypatch, medium_id: int):
    """While Dev.to is mid-call, the Medium worker commits its success."""

    def publish(_self, request, credentials):
        other = TestSession()
        try:
            row = other.get(Publication, medium_id)
            row.status = PublicationStatus.PUBLISHED
            row.published_at = utcnow()
            publishing_service.sync_content_status(row.content)
            other.commit()
        finally:
            other.close()
        return PublishResult(external_id="1", external_url="https://dev.to/x/1")

    monkeypatch.setattr(DevToAdapter, "publish", publish)


def test_the_second_platform_to_land_does_not_announce_again(db, two_rows, monkeypatch):
    devto, medium = two_rows
    _other_worker_lands_first(monkeypatch, medium.id)
    announced = []
    monkeypatch.setattr(
        publishing_service,
        "_notify_published",
        lambda _db, content, publication: announced.append(publication.id),
    )

    publishing_service.execute(db, devto)

    db.expire_all()
    assert db.get(Publication, devto.id).status == PublicationStatus.PUBLISHED
    assert db.get(Content, devto.content_id).status == ContentStatus.PUBLISHED
    # The Medium worker made the transition; Dev.to landing second is not news.
    assert announced == []


def test_the_first_platform_to_land_still_announces(db, two_rows, monkeypatch):
    devto, _ = two_rows
    monkeypatch.setattr(
        DevToAdapter,
        "publish",
        lambda _self, request, credentials: PublishResult(
            external_id="1", external_url="https://dev.to/x/1"
        ),
    )
    announced = []
    monkeypatch.setattr(
        publishing_service,
        "_notify_published",
        lambda _db, content, publication: announced.append(publication.id),
    )

    publishing_service.execute(db, devto)

    assert announced == [devto.id]
