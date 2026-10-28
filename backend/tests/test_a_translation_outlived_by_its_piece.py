"""A translation whose piece is deleted while the model is working.

``translate`` commits the row ``PENDING`` and then waits tens of seconds on the
model with no transaction open — so the piece can be deleted in the meantime,
and its translations go with it. Writing the answer (or the failure) to the
row afterwards raised ``ObjectDeletedError``, from inside the very handler
meant to record the failure: a 500 for a piece the user had just deleted.
It is now a 404 that says what happened, and nothing is written.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation
from app.services import ai, translation
from tests.conftest import TestSession

BODY = "# Publishing with Pulse\n\n" + "Pulse turns repository activity into finished posts. " * 5


@pytest.fixture
def piece(db, project) -> int:
    content = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Testing translations",
        slug="testing-translations",
        body_markdown=BODY,
        status=ContentStatus.DRAFT,
    )
    db.add(content)
    db.commit()
    return content.id


def _deleted_by_another_request(content_id: int) -> None:
    other = TestSession()
    other.delete(other.get(Content, content_id))
    other.commit()
    other.close()


def test_an_answer_for_a_deleted_piece_is_a_404(client, auth, piece, db, monkeypatch):
    def model(*a, **kw):
        _deleted_by_another_request(piece)
        return {"title": "Titre", "body_markdown": BODY}, SimpleNamespace(provider="p", model="m")

    monkeypatch.setattr(ai, "json_completion", model)

    resp = client.post(f"/api/v1/content/{piece}/translations", headers=auth, json={"language": "fr"})

    assert resp.status_code == 404, resp.text
    assert "deleted while it was being translated" in resp.json()["detail"]
    db.expire_all()
    assert db.query(ContentTranslation).count() == 0


def test_a_provider_failure_for_a_deleted_piece_is_a_404(client, auth, piece, db, monkeypatch):
    def model(*a, **kw):
        _deleted_by_another_request(piece)
        raise ai.AIError("every provider failed")

    monkeypatch.setattr(ai, "json_completion", model)

    resp = client.post(f"/api/v1/content/{piece}/translations", headers=auth, json={"language": "fr"})

    assert resp.status_code == 404, resp.text


def test_a_live_piece_still_translates(client, auth, piece, monkeypatch):
    monkeypatch.setattr(
        ai,
        "json_completion",
        lambda *a, **kw: ({"title": "Titre", "body_markdown": BODY}, SimpleNamespace(provider="p", model="m")),
    )

    resp = client.post(f"/api/v1/content/{piece}/translations", headers=auth, json={"language": "fr"})

    assert resp.status_code in (200, 201), resp.text
    assert translation.TranslationSourceGone.__mro__[1] is translation.TranslationError
