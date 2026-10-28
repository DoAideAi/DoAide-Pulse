"""A language that already has a row is not translated twice at once (C105 M3).

Only the first translation into a language was guarded — by the unique
constraint on insert. Every later one went through ``upsert_pending``, which set
the existing row back to ``pending`` whatever it already said: a retry pressed
twice, or two tabs, both paid for a model call and whichever finished last
silently replaced the other. The existing row is now claimed by a conditional
write. A ``pending`` row old enough to have been abandoned by a dead request can
be taken over, or it would never leave that state.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.mixins import utcnow
from app.models.translation import ContentTranslation, TranslationStatus
from app.services import ai, translation

BODY = (
    "# Publishing with Pulse\n\n"
    "Pulse turns your repository activity into finished posts. Connect a "
    "GitHub account, choose the repository you want watched, and every release "
    "becomes a complete draft waiting for your review.\n"
)


@pytest.fixture
def content(db, project):
    c = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, title="T",
        slug="t", body_markdown=BODY, status=ContentStatus.DRAFT,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _row(db, content, status, *, age_minutes=0):
    row = ContentTranslation(
        content_id=content.id, language="fr", status=status, title="Ancien",
        body_markdown="Ancien texte",
    )
    db.add(row)
    db.flush()
    row.updated_at = utcnow() - timedelta(minutes=age_minutes)
    db.commit()
    return row


def _answers(monkeypatch):
    calls = []

    def answer(*a, **kw):
        calls.append(1)
        return {"title": "Nouveau", "body_markdown": BODY}, SimpleNamespace(provider="p", model="m")

    monkeypatch.setattr(ai, "json_completion", answer)
    return calls


def test_a_fresh_pending_row_is_in_progress_and_no_model_is_called(db, content, monkeypatch):
    row = _row(db, content, TranslationStatus.PENDING, age_minutes=1)
    calls = _answers(monkeypatch)

    with pytest.raises(translation.TranslationInProgress):
        translation.translate(db, content, "fr")

    assert calls == []
    db.refresh(row)
    assert row.status == TranslationStatus.PENDING
    assert row.title == "Ancien"


def test_the_api_answers_409(client, auth, db, content, monkeypatch):
    _row(db, content, TranslationStatus.PENDING, age_minutes=1)
    _answers(monkeypatch)
    resp = client.post(
        f"/api/v1/content/{content.id}/translations", headers=auth, json={"language": "fr"}
    )
    assert resp.status_code == 409, resp.text


def test_an_abandoned_pending_row_can_be_taken_over(db, content, monkeypatch):
    stale = translation.PENDING_STALE_AFTER.total_seconds() / 60 + 5
    _row(db, content, TranslationStatus.PENDING, age_minutes=stale)
    calls = _answers(monkeypatch)

    row = translation.translate(db, content, "fr")

    assert calls == [1]
    assert row.status in (TranslationStatus.READY, TranslationStatus.NEEDS_REVIEW)
    assert row.title == "Nouveau"


@pytest.mark.parametrize(
    "status", [TranslationStatus.READY, TranslationStatus.NEEDS_REVIEW, TranslationStatus.FAILED]
)
def test_a_settled_row_can_be_translated_again(db, content, monkeypatch, status):
    _row(db, content, status)
    calls = _answers(monkeypatch)

    row = translation.translate(db, content, "fr")

    assert calls == [1]
    assert row.title == "Nouveau"
