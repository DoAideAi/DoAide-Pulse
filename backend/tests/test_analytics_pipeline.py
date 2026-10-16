"""Content by status and publish success rates, per account and per platform."""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus

URL = "/api/v1/analytics/pipeline"


def _piece(db, project, title, status):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title=title,
        slug=title.lower().replace(" ", "-"),
        body_markdown="word " * 50,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def _pub(db, content, platform, status):
    db.add(Publication(content_id=content.id, platform=platform, status=status))


def test_an_empty_account_has_zero_counts_and_no_rate(client, auth):
    resp = client.get(URL, headers=auth)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert all(row["count"] == 0 for row in body["content_by_status"])
    assert body["publications"]["success_rate"] is None
    assert body["by_platform"] == []


def test_counts_statuses_and_rates_settled_publications_only(client, auth, db, project):
    # One publication per (piece, platform), so each Dev.to outcome is its own piece.
    pieces = [
        _piece(db, project, title, ContentStatus.PUBLISHED) for title in ("A", "B", "C")
    ]
    failed = _piece(db, project, "D", ContentStatus.FAILED)
    _piece(db, project, "Two", ContentStatus.DRAFT)
    _piece(db, project, "Three", ContentStatus.DRAFT)
    for piece in pieces:
        _pub(db, piece, Platform.DEVTO, PublicationStatus.PUBLISHED)
    _pub(db, failed, Platform.DEVTO, PublicationStatus.FAILED)
    _pub(db, pieces[0], Platform.HASHNODE, PublicationStatus.SCHEDULED)
    db.commit()

    body = client.get(URL, headers=auth).json()

    statuses = {row["status"]: row["count"] for row in body["content_by_status"]}
    assert statuses["published"] == 3
    assert statuses["failed"] == 1
    assert statuses["draft"] == 2
    assert body["publications"] == {
        "published": 3,
        "failed": 1,
        "in_flight": 1,
        "cancelled": 0,
        "success_rate": 0.75,
    }
    devto, hashnode = body["by_platform"]
    assert devto["platform"] == "devto" and devto["success_rate"] == 0.75
    # Scheduled is neither a success nor a failure yet.
    assert hashnode["in_flight"] == 1 and hashnode["success_rate"] is None


def test_needs_a_signed_in_user(client):
    assert client.get(URL).status_code == 401
