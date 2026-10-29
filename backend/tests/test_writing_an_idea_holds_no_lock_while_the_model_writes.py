"""Writing an idea claims it briefly instead of holding its row lock throughout.

``POST /content/ideas/{id}/write`` read the idea ``FOR UPDATE`` and kept that
lock — and the pooled connection under it — for the whole model call: twenty
seconds, minutes under retries. Everything that touched the idea waited behind
it: a second click (holding a connection of its own while it waited), planning
or dismissing it on the calendar, and deleting the project, whose cascade needs
the idea's row.

The idea is now claimed (``source.writing_since``) under a lock that lasts one
commit; the model call runs with no lock and no connection held; a second
request answers 409 while a fresh claim stands, and a claim older than
``IDEA_CLAIM_SECONDS`` — a worker that died mid-write — can be taken over.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.content import Content, ContentIdea, ContentType
from app.models.mixins import utcnow
from app.routers import content as content_router
from app.services import content_generator
from app.services.content_generator import GeneratedContent

V1 = "/api/v1"


@pytest.fixture
def idea(db, project) -> ContentIdea:
    row = ContentIdea(
        project_id=project.id, content_type=ContentType.ANNOUNCEMENT,
        headline="Retries that never post twice", rationale="People ask.",
        source={"kind": "test"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _generated():
    return GeneratedContent(
        title="Generated", body_markdown="Body.\n\n" + "word " * 200, excerpt="x",
        meta_description="m", keywords=["retries"], tags=["python"], confidence=0.5,
    )


def test_no_transaction_is_open_while_the_model_writes(client, auth, db, idea, monkeypatch):
    seen = {}

    def generate(project, content_type, **kwargs):
        seen["in_transaction"] = db.in_transaction()
        return _generated()

    monkeypatch.setattr(content_generator, "generate", generate)

    resp = client.post(f"{V1}/content/ideas/{idea.id}/write", headers=auth)

    assert resp.status_code == 201, resp.text
    assert seen["in_transaction"] is False


def test_the_claim_is_cleared_once_the_draft_is_written(client, auth, db, idea, monkeypatch):
    monkeypatch.setattr(content_generator, "generate", lambda *a, **k: _generated())

    resp = client.post(f"{V1}/content/ideas/{idea.id}/write", headers=auth)

    assert resp.status_code == 201
    db.expire_all()
    row = db.get(ContentIdea, idea.id)
    assert row.used_content_id == resp.json()["id"]
    assert "writing_since" not in (row.source or {})


def test_a_second_request_during_a_fresh_claim_is_told_so(client, auth, db, idea, monkeypatch):
    called = []
    monkeypatch.setattr(content_generator, "generate", lambda *a, **k: called.append(1))
    idea.source = {**idea.source, "writing_since": utcnow().isoformat()}
    db.commit()

    resp = client.post(f"{V1}/content/ideas/{idea.id}/write", headers=auth)

    assert resp.status_code == 409
    assert called == []


def test_an_abandoned_claim_can_be_taken_over(client, auth, db, idea, monkeypatch):
    monkeypatch.setattr(content_generator, "generate", lambda *a, **k: _generated())
    stale = utcnow() - timedelta(seconds=content_router.IDEA_CLAIM_SECONDS + 60)
    idea.source = {**idea.source, "writing_since": stale.isoformat()}
    db.commit()

    resp = client.post(f"{V1}/content/ideas/{idea.id}/write", headers=auth)

    assert resp.status_code == 201, resp.text


def test_a_failed_generation_lets_the_idea_be_written_again(client, auth, db, idea, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(content_generator, "generate", boom)
    with pytest.raises(RuntimeError):
        client.post(f"{V1}/content/ideas/{idea.id}/write", headers=auth)

    db.expire_all()
    assert "writing_since" not in (db.get(ContentIdea, idea.id).source or {})
    assert db.query(Content).count() == 0
