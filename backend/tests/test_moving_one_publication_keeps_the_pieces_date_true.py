"""Moving one publication on the calendar keeps the piece's own date true.

``PATCH /calendar/content/{id}`` with a ``publication_id`` moves that one row
and left ``content.scheduled_for`` where it was. For a piece with one
publication that is the whole schedule: moved from Tuesday to Friday, it went
out Friday while the editor said Tuesday — one fact spelled two ways, the
pairing the content PATCH already refuses to leave behind. The piece's date is
now the earliest time among its publications still waiting to go out.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus

V1 = "/api/v1"


# One clock reading for the whole module, so "+3 days" means the same instant
# in the fixture and in the assertion.
_NOW = datetime.now(UTC).replace(microsecond=0)


def _at(days):
    return _NOW + timedelta(days=days)


@pytest.fixture
def piece(db, project):
    content = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, title="Retries",
        slug="retries", body_markdown="Body " * 300, excerpt="x",
        status=ContentStatus.APPROVED, scheduled_for=_at(2),
    )
    db.add(content)
    db.flush()
    rows = [
        Publication(content_id=content.id, platform=Platform.DEVTO,
                    status=PublicationStatus.SCHEDULED, scheduled_for=_at(2)),
        Publication(content_id=content.id, platform=Platform.HASHNODE,
                    status=PublicationStatus.SCHEDULED, scheduled_for=_at(3)),
    ]
    db.add_all(rows)
    db.commit()
    return content, rows


def _move(client, auth, content, publication, when):
    return client.patch(
        f"{V1}/calendar/content/{content.id}",
        headers=auth,
        json={"scheduled_for": when.isoformat(), "publication_id": publication.id},
    )


def _date(db, content):
    db.expire_all()
    value = db.get(Content, content.id).scheduled_for
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def test_moving_the_earliest_row_later_moves_the_pieces_date(client, auth, db, piece):
    content, (devto, hashnode) = piece

    resp = _move(client, auth, content, devto, _at(5))

    assert resp.status_code == 200, resp.text
    # Hashnode, at +3 days, is now the first thing to go out.
    assert _date(db, content) == _at(3)


def test_moving_a_row_earlier_brings_the_pieces_date_forward(client, auth, db, piece):
    content, (_, hashnode) = piece

    _move(client, auth, content, hashnode, _at(1))

    assert _date(db, content) == _at(1)
