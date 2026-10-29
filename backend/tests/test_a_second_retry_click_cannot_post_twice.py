"""Two Retry clicks cannot put one publication on a platform twice.

``POST /content/{id}/retry/{publication_id}`` checked that the row was failed
or cancelled and then re-armed it with plain attribute writes. Two clicks both
read it failed; the first re-armed and dispatched it, and its worker took the
row to ``publishing`` and then ``published``; the second then wrote
``pending``, ``attempts=0`` over that and dispatched it again. Where the piece
itself did not change — one platform failed on a piece already live elsewhere —
no version check stood in the way, and the post went out a second time.

The re-arm is now a conditional UPDATE on the state the check approved, so
only one of the clicks can move a stopped row back into the queue.
"""
from __future__ import annotations

import pytest
from sqlalchemy import update

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus
from app.routers import content as content_router
from app.services import publishing_service

API = "/api/v1/content"


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.PUBLISHED,
        title="Live on one platform",
        slug="live-on-one",
        body_markdown="Body.",
    )
    db.add(row)
    db.commit()
    db.add_all(
        [
            Publication(
                content_id=row.id, platform=Platform.DEVTO, status=PublicationStatus.PUBLISHED
            ),
            Publication(
                content_id=row.id,
                platform=Platform.HASHNODE,
                status=PublicationStatus.FAILED,
                attempts=3,
                error="503",
            ),
        ]
    )
    db.commit()
    db.refresh(row)
    return row


def _failed(db, piece) -> Publication:
    return db.query(Publication).filter_by(content_id=piece.id, platform=Platform.HASHNODE).one()


@pytest.fixture
def first_click_wins_meanwhile(db, monkeypatch):
    """While this request re-arms, the other click and its worker publish the row."""
    real = publishing_service.retry_hold

    def hold(content, publication):
        db.execute(
            update(Publication)
            .where(Publication.id == publication.id)
            .values(status=PublicationStatus.PUBLISHED, attempts=1, error=None)
            .execution_options(synchronize_session=False)
        )
        # The other click's transaction, committed: the suite shares one
        # session, so without this the refusal's rollback would undo it too.
        db.commit()
        return real(content, publication)

    monkeypatch.setattr(publishing_service, "retry_hold", hold)


def test_the_late_click_is_refused_and_nothing_is_sent_again(
    client, auth, db, piece, first_click_wins_meanwhile, monkeypatch
):
    sent: list[list[int]] = []
    monkeypatch.setattr(content_router, "_dispatch", sent.append)
    publication = _failed(db, piece)

    resp = client.post(f"{API}/{piece.id}/retry/{publication.id}", headers=auth)

    assert resp.status_code == 409, resp.text
    assert sent == []
    db.expire_all()
    assert _failed(db, piece).status == PublicationStatus.PUBLISHED


def test_the_piece_wide_retry_skips_the_row_it_lost(
    client, auth, db, piece, first_click_wins_meanwhile, monkeypatch
):
    sent: list[list[int]] = []
    monkeypatch.setattr(content_router, "_dispatch", lambda ids: sent.append(list(ids)))

    resp = client.post(f"{API}/{piece.id}/retry", headers=auth)

    assert resp.status_code == 200, resp.text
    assert resp.json()["retried"] == []
    assert all(not ids for ids in sent)
    db.expire_all()
    assert _failed(db, piece).status == PublicationStatus.PUBLISHED


def test_an_uncontested_retry_still_re_arms_and_dispatches(
    client, auth, db, piece, monkeypatch
):
    sent: list[list[int]] = []
    monkeypatch.setattr(content_router, "_dispatch", lambda ids: sent.append(list(ids)))
    publication = _failed(db, piece)

    resp = client.post(f"{API}/{piece.id}/retry/{publication.id}", headers=auth)

    assert resp.status_code == 200, resp.text
    assert sent == [[publication.id]]
    db.expire_all()
    row = _failed(db, piece)
    assert (row.status, row.attempts, row.error) == (PublicationStatus.PENDING, 0, None)
