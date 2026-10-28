"""A piece with no body is not queued for a destination that publishes the body.

Dev.to and Git refused it at the worker, after the endpoint had answered
"queued"; Hashnode, Medium and WordPress posted an empty article; Buttondown
emailed the whole list a subject line and a link.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.publication import Platform


@pytest.fixture
def empty_piece(db, project):
    row = Content(
        project_id=project.id,
        content_type=ContentType.ANNOUNCEMENT,
        status=ContentStatus.APPROVED,
        title="Nothing yet",
        slug="nothing-yet",
        body_markdown="  \n\n ",
        excerpt="A short teaser.",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.mark.parametrize("platform", [Platform.BUTTONDOWN, Platform.DEVTO])
def test_an_empty_body_is_refused_for_an_article_destination(
    db, client, auth, empty_piece, connect, platform
):
    connect(platform)
    resp = client.post(
        f"/api/v1/content/{empty_piece.id}/publish",
        headers=auth,
        json={"platforms": [platform.value]},
    )
    assert resp.status_code == 422, resp.text
    assert "no body" in resp.json()["detail"]
    db.expire_all()
    assert db.get(Content, empty_piece.id).publications == []


def test_a_short_form_destination_still_takes_it(db, client, auth, empty_piece, connect):
    """Mastodon composes from the excerpt; the body is not what it posts."""
    connect(Platform.MASTODON)
    resp = client.post(
        f"/api/v1/content/{empty_piece.id}/publish",
        headers=auth,
        json={
            "platforms": ["mastodon"],
            "scheduled_for": (utcnow() + timedelta(days=2)).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
