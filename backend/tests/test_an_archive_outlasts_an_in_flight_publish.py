"""Archiving a piece is not undone by a publish that was already in flight.

``execute`` drops a row whose piece is archived — but it checks before the
platform call, and a worker can claim a row moments before the user archives
the piece. ``sync_content_status`` then derived the status from the rows alone:
one successful publication made the piece ``published`` again, quietly undoing
the archive. Leaving the archive is a deliberate act (a ``PATCH`` to another
status); a worker finishing its work is not one.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import PublishResult
from app.services.publishers.devto import DevToAdapter
from tests.conftest import TestSession


@pytest.fixture
def armed(db, user, project) -> Publication:
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
    row = Publication(content_id=piece.id, platform=Platform.DEVTO, status=PublicationStatus.PENDING)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _archived_during_the_call(monkeypatch, content_id):
    def publish(_self, request, credentials):
        other = TestSession()
        other.get(Content, content_id).status = ContentStatus.ARCHIVED
        other.commit()
        other.close()
        return PublishResult(external_id="1", external_url="https://dev.to/x/1")

    monkeypatch.setattr(DevToAdapter, "publish", publish)


def test_a_publish_that_lands_after_the_archive_leaves_it_archived(db, armed, monkeypatch):
    content_id = armed.content_id
    _archived_during_the_call(monkeypatch, content_id)

    publishing_service.execute(db, armed)

    db.expire_all()
    piece = db.get(Content, content_id)
    assert piece.status == ContentStatus.ARCHIVED
    # The post is live, and that is still recorded.
    assert db.get(Publication, armed.id).status == PublicationStatus.PUBLISHED
    assert piece.published_at is not None


def test_sync_leaves_an_archived_piece_archived_whatever_its_rows_say(db, armed):
    piece = db.get(Content, armed.content_id)
    piece.status = ContentStatus.ARCHIVED
    armed.status = PublicationStatus.FAILED
    db.commit()

    publishing_service.sync_content_status(piece)

    assert piece.status == ContentStatus.ARCHIVED


def test_an_unarchived_piece_is_still_derived_from_its_rows(db, armed):
    piece = db.get(Content, armed.content_id)
    armed.status = PublicationStatus.PUBLISHED
    db.commit()

    publishing_service.sync_content_status(piece)

    assert piece.status == ContentStatus.PUBLISHED
