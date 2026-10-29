"""Moving a piece on the calendar cannot re-arm a row a worker has just claimed.

``PATCH /calendar/content/{id}`` refuses rows that are ``publishing`` or
``published`` — re-arming one is how a post goes out twice. But the refusal
read the status the request had loaded and then wrote with a plain UPDATE, so
a sweep that claimed the row in between (``publish_one``'s conditional claim)
had ``publishing`` overwritten with ``scheduled``: the worker posted it, and
the next sweep posted it again.

The interleaving is staged by moving the row to ``publishing`` in the database
while the session still holds the copy that says ``scheduled`` — which is what
a request that read it a moment earlier is holding.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm.attributes import set_committed_value

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus

V1 = "/api/v1"


@pytest.fixture(params=[PublicationStatus.SCHEDULED, PublicationStatus.PENDING])
def scheduled(db, project, request):
    content = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, title="Retries",
        slug="retries", body_markdown="Body " * 300, excerpt="x",
        status=ContentStatus.APPROVED,
    )
    db.add(content)
    db.flush()
    # Both waiting states. A ``pending`` row is the one whose status the move
    # changes, so it is the one whose ``publishing`` was overwritten outright;
    # a ``scheduled`` row kept its status by accident of the ORM writing only
    # changed columns, and had its time and attempt count rewritten under the
    # worker instead.
    pub = Publication(
        content_id=content.id, platform=Platform.DEVTO,
        status=request.param, attempts=1,
        scheduled_for=(
            datetime.now(UTC) + timedelta(minutes=1)
            if request.param is PublicationStatus.SCHEDULED else None
        ),
    )
    db.add(pub)
    db.commit()
    # Loaded: the request below will find this instance, status and all.
    assert pub.status is request.param
    return content, pub


def _worker_claims(db, pub):
    """Commit the claim, as the worker's own transaction would, and leave the
    session's instance saying what it said before — the stale read."""
    seen = pub.status
    db.execute(
        update(Publication)
        .where(Publication.id == pub.id)
        .values(status=PublicationStatus.PUBLISHING)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    set_committed_value(pub, "status", seen)
    set_committed_value(pub, "attempts", 1)


def test_a_row_claimed_meanwhile_is_left_to_its_worker(client, auth, db, scheduled):
    content, pub = scheduled
    _worker_claims(db, pub)

    resp = client.patch(
        f"{V1}/calendar/content/{content.id}",
        headers=auth,
        json={"scheduled_for": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
    )

    assert resp.status_code == 409, resp.text
    db.expire_all()
    row = db.get(Publication, pub.id)
    assert row.status is PublicationStatus.PUBLISHING
    assert row.attempts == 1, "the worker's attempt count was reset under it"


def test_a_row_still_waiting_moves(client, auth, db, scheduled):
    content, pub = scheduled
    moved = datetime.now(UTC) + timedelta(days=2)

    resp = client.patch(
        f"{V1}/calendar/content/{content.id}",
        headers=auth,
        json={"scheduled_for": moved.isoformat()},
    )

    assert resp.status_code == 200, resp.text
    db.expire_all()
    row = db.get(Publication, pub.id)
    assert row.status is PublicationStatus.SCHEDULED
    assert abs((row.scheduled_for.replace(tzinfo=UTC) - moved).total_seconds()) < 1
