"""A credential refused mid-publish condemns that credential, not its replacement.

A publish attempt loads the connection, decrypts its credentials and calls the
platform — which can take a while. A token rejection then marked *the row
loaded at the start* INVALID. Two things the user may have done meanwhile:

* **Reconnected** — saved fresh, working credentials, which is exactly what
  an "expired token" error invites. The stale write marked the *new*
  credentials INVALID, and every later publish failed as not connected.
* **Disconnected** — deleted the row. The write then updated a deleted row,
  and the ``StaleDataError`` rolled back this publication's own failure.

Invalidation is now a conditional UPDATE on the ciphertext the attempt used.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import publishing_service
from app.services.crypto import encrypt_credentials
from app.services.publishers.base import CredentialError
from app.services.publishers.devto import DevToAdapter
from tests.conftest import TestSession


@pytest.fixture
def publication(db, user, project) -> Publication:
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
            encrypted_credentials=encrypt_credentials({"api_key": "old-expired"}),
        )
    )
    db.commit()
    row = Publication(content_id=piece.id, platform=Platform.DEVTO, status=PublicationStatus.PENDING)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _refuse_after(monkeypatch, meanwhile):
    def publish(_self, request, credentials):
        assert credentials["api_key"] == "old-expired"
        meanwhile()
        raise CredentialError("Dev.to rejected the API key.")

    monkeypatch.setattr(DevToAdapter, "publish", publish)


def _other_session(work):
    other = TestSession()
    try:
        work(other)
        other.commit()
    finally:
        other.close()


def test_a_reconnect_during_the_attempt_survives_the_old_token_s_rejection(
    db, user, publication, monkeypatch
):
    def reconnect(session):
        row = session.query(PlatformConnection).filter_by(user_id=user.id).one()
        row.encrypted_credentials = encrypt_credentials({"api_key": "fresh-and-valid"})
        row.status = ConnectionStatus.CONNECTED

    _refuse_after(monkeypatch, lambda: _other_session(reconnect))

    publishing_service.execute(db, publication)

    db.expire_all()
    connection = db.query(PlatformConnection).filter_by(user_id=user.id).one()
    assert connection.status == ConnectionStatus.CONNECTED
    assert db.get(Publication, publication.id).status == PublicationStatus.FAILED


def test_a_disconnect_during_the_attempt_still_records_the_failure(
    db, user, publication, monkeypatch
):
    def disconnect(session):
        session.query(PlatformConnection).filter_by(user_id=user.id).delete()

    _refuse_after(monkeypatch, lambda: _other_session(disconnect))

    publishing_service.execute(db, publication)

    db.expire_all()
    assert db.query(PlatformConnection).count() == 0
    assert db.get(Publication, publication.id).status == PublicationStatus.FAILED


def test_an_unchanged_connection_is_still_marked_invalid(db, user, publication, monkeypatch):
    _refuse_after(monkeypatch, lambda: None)

    publishing_service.execute(db, publication)

    db.expire_all()
    connection = db.query(PlatformConnection).filter_by(user_id=user.id).one()
    assert connection.status == ConnectionStatus.INVALID
    assert "rejected" in connection.last_error
