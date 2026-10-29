"""The AI assists hand their connection back before the model call.

``POST /content/generate`` learned this first: a request reads a row, then
waits seconds — minutes under retries — on a model, and the read left its pool
connection checked out and idle in a transaction for all of it. The pool is
fifteen per process, so a handful of overlapping calls starved every other
page of connections. Generate releases first (``release_for_slow_work``);
repurpose, the inline passage edit and the headline variants, which do the
same read-then-wait, did not.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.services import headlines, inline_edit, repurpose

V1 = "/api/v1"
BODY = "First paragraph here.\n\nSecond paragraph, which is the one to shorten."


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Retries that never post twice",
        slug="retries",
        body_markdown=BODY,
        excerpt="Retries.",
        status=ContentStatus.DRAFT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _spy(db, real, seen):
    def wrapper(*args, **kwargs):
        seen["in_transaction"] = db.in_transaction()
        return real(*args, **kwargs)

    return wrapper


def test_repurpose_releases_first(client, auth, db, piece, project, monkeypatch):
    seen = {}
    monkeypatch.setattr(repurpose, "generate", _spy(db, repurpose.generate, seen))

    resp = client.post(f"{V1}/content/{piece.id}/repurpose", headers=auth)

    assert resp.status_code == 200, resp.text
    assert seen == {"in_transaction": False}


def test_the_passage_edit_releases_first(client, auth, db, piece, monkeypatch):
    seen = {}
    monkeypatch.setattr(inline_edit, "edit", _spy(db, inline_edit.edit, seen))

    resp = client.post(
        f"{V1}/content/{piece.id}/edit",
        headers=auth,
        json={"selection": "Second paragraph", "operation": "shorten"},
    )

    # 200 with a provider, 503 without one: either way the call was made with
    # the connection already back in the pool.
    assert resp.status_code in (200, 503), resp.text
    assert seen == {"in_transaction": False}


def test_the_headline_variants_release_first(client, auth, db, piece, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        headlines, "generate_variants", _spy(db, headlines.generate_variants, seen)
    )

    resp = client.post(f"{V1}/content/{piece.id}/headlines", headers=auth)

    assert resp.status_code == 200, resp.text
    assert seen == {"in_transaction": False}


def test_the_passage_check_still_runs_before_the_model(client, auth, db, piece, monkeypatch):
    """Releasing must not skip the guard that the selection is in the saved body."""
    called = []
    monkeypatch.setattr(inline_edit, "edit", lambda **kw: called.append(kw))

    resp = client.post(
        f"{V1}/content/{piece.id}/edit",
        headers=auth,
        json={"selection": "not in the body at all", "operation": "shorten"},
    )

    assert resp.status_code == 422
    assert called == []
