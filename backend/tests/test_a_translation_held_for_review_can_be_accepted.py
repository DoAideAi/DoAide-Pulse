"""A translation held for review can be accepted by the person who read it.

``needs_review`` is documented as "publishable by a human who has read it",
but nothing let the human say so: ``for_publishing`` falls back to the
original while ``quality_issues`` is non-empty, and no route cleared it. The
state had no way forward — delete it, or translate again and hope.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation, TranslationStatus
from app.services import translation

ISSUES = [{"code": "length", "message": "Much shorter than the original."}]


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.APPROVED,
        title="Retries",
        slug="retries",
        body_markdown="How retries work. " * 40,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _french(db, piece, status=TranslationStatus.NEEDS_REVIEW, *, issues=ISSUES, version=None):
    row = ContentTranslation(
        content_id=piece.id,
        language="fr",
        status=status,
        title="Les relances",
        body_markdown="Comment fonctionnent les relances. " * 30,
        source_version=piece.version if version is None else version,
        quality_issues=issues,
    )
    db.add(row)
    db.commit()
    return row


URL = "/api/v1/content/{}/translations/fr/accept"


def test_accepting_makes_it_the_text_that_publishes(client, auth, db, piece):
    _french(db, piece)
    before = translation.for_publishing(db, piece, "fr")
    assert before.translation is None and "quality issue" in before.reason

    resp = client.post(URL.format(piece.id), headers=auth)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"
    assert resp.json()["quality_issues"] == []
    db.expire_all()
    after = translation.for_publishing(db, db.get(Content, piece.id), "fr")
    assert after.language == "fr" and after.translation is not None


@pytest.mark.parametrize(
    "status", [TranslationStatus.PENDING, TranslationStatus.FAILED, TranslationStatus.READY]
)
def test_only_a_translation_waiting_for_review_can_be_accepted(client, auth, db, piece, status):
    _french(db, piece, status, issues=[])

    resp = client.post(URL.format(piece.id), headers=auth)

    assert resp.status_code == 409
    assert "waiting for review" in resp.json()["detail"]


def test_a_stale_translation_cannot_be_signed_off(client, auth, db, piece):
    _french(db, piece, version=0)  # made before the piece's current version

    resp = client.post(URL.format(piece.id), headers=auth)

    assert resp.status_code == 409
    assert "edited since" in resp.json()["detail"]
    db.expire_all()
    row = db.query(ContentTranslation).one()
    assert row.status == TranslationStatus.NEEDS_REVIEW and row.quality_issues


def test_no_translation_is_a_404(client, auth, piece):
    assert client.post(URL.format(piece.id), headers=auth).status_code == 404
