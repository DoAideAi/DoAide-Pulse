"""``GET /content/queue/publications?status=`` narrows the queue to one state.

The sidebar's failed-publications badge counted failed rows on the first page
of the queue — 50 rows, every state — so a failure behind fifty pending
publications was never counted. With a filter, ``limit=1`` and
``X-Total-Count`` the badge reads the real number.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus


def _seed(db, project, *, pending: int, failed: int) -> None:
    # One piece per row: a piece has at most one publication per platform.
    states = [PublicationStatus.PENDING] * pending + [PublicationStatus.FAILED] * failed
    for i, state in enumerate(states):
        content = Content(
            project_id=project.id,
            content_type=ContentType.TUTORIAL,
            title=f"T{i}",
            slug=f"t{i}",
            status=ContentStatus.APPROVED,
        )
        db.add(content)
        db.flush()
        db.add(Publication(content_id=content.id, platform=Platform.DEVTO, status=state))
    db.commit()


def test_failed_rows_past_the_first_page_are_counted(client, auth, db, project):
    _seed(db, project, pending=60, failed=3)
    resp = client.get(
        "/api/v1/content/queue/publications?status=failed&limit=1", headers=auth
    )
    assert resp.status_code == 200
    assert resp.headers["x-total-count"] == "3"
    assert [p["status"] for p in resp.json()] == ["failed"]


def test_no_filter_is_the_whole_queue(client, auth, db, project):
    _seed(db, project, pending=2, failed=1)
    resp = client.get("/api/v1/content/queue/publications", headers=auth)
    assert resp.headers["x-total-count"] == "3"


def test_a_state_the_queue_does_not_hold_is_refused(client, auth):
    resp = client.get("/api/v1/content/queue/publications?status=published", headers=auth)
    assert resp.status_code == 422
    assert "not in it" in resp.json()["detail"]
