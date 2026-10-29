"""Approving a piece banks the text the reviewer approved before Pulse tidies it.

On the way to ``approved`` the SEO autofix rewrites the title, the meta
description and the body. Every other writer of those columns snapshots the
text it replaces; this one did not, and the UPDATE carrying its changes moved
``version`` on — so the words the reviewer actually signed off were stored
under no version at all, and the history's Restore could not bring them back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.content import Content, ContentStatus, ContentType
from app.models.revision import ContentRevision, RevisionSource

V1 = "/api/v1"

# 80 characters; the autofix keeps the part before the colon (56).
LONG_TITLE = "Shipping retries that never post twice to the same place: a field guide"
BODY = (
    "Retries are where duplicate posts come from. " * 30
    + "\n\n## Why\n\nBecause the worker cannot tell a timeout from a failure.\n"
)


@pytest.fixture(autouse=True)
def quality_gate_on(monkeypatch):
    """The suite runs with the gate off; approving only tidies with it on."""
    monkeypatch.setattr(settings, "content_quality_gate_enabled", True)


@pytest.fixture
def draft(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title=LONG_TITLE,
        slug="shipping-retries",
        body_markdown=BODY,
        excerpt="Retries without duplicates.",
        meta_description="",
        status=ContentStatus.REVIEW,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _system_revisions(db, content_id):
    return list(
        db.scalars(
            select(ContentRevision).where(
                ContentRevision.content_id == content_id,
                ContentRevision.source == RevisionSource.SYSTEM,
            )
        )
    )


@pytest.mark.parametrize("force", [False, True])
def test_approving_banks_the_approved_title(client, auth, db, draft, force):
    version = draft.version
    resp = client.post(
        f"{V1}/content/{draft.id}/approve" + ("?force=true" if force else ""), headers=auth
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] != LONG_TITLE, "the autofix should have shortened it"

    banked = _system_revisions(db, draft.id)
    assert len(banked) == 1
    assert banked[0].title == LONG_TITLE
    assert banked[0].body_markdown == BODY
    assert banked[0].revision == version
    assert "title" in banked[0].note


def test_bulk_approve_banks_it_too(client, auth, db, draft):
    resp = client.post(
        f"{V1}/content/bulk/approve", headers=auth, json={"content_ids": [draft.id]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["succeeded"] == [draft.id]
    assert [r.title for r in _system_revisions(db, draft.id)] == [LONG_TITLE]


def test_nothing_is_banked_when_the_autofix_changes_nothing(client, auth, db, draft):
    draft.title = "Shipping retries that never post twice to one place"
    db.commit()
    resp = client.post(f"{V1}/content/{draft.id}/approve", headers=auth)
    assert resp.status_code == 200, resp.text
    banked = _system_revisions(db, draft.id)
    assert all(r.title == draft.title for r in banked)
    assert not [r for r in banked if "title" in r.note]
