"""A model that answers without a translation does not overwrite the old one.

``translate`` wrote whatever came back. An answer with no body — ``{}``, an
empty string, ``null``, or an object where text was asked for — was stored as
the translation, replacing the text a previous run had produced, although the
module promises that a failed retry "leaves the user with the translation they
already had". And ``ai.as_str`` turned an object into its Python repr, so
``{"body_markdown": {"a": 1}}`` was saved as the text ``{'a': 1}``.

Now an answer without a usable body is a provider failure: the row is marked
``failed``, its previous text is kept, and the caller gets the retryable 503.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation, TranslationStatus
from app.services import ai, translation

BODY = "# Publishing with Pulse\n\n" + "Pulse turns repository activity into finished posts. " * 5
GOOD = "# Publier avec Pulse\n\n" + "Pulse transforme l'activité du dépôt en articles finis. " * 5


@pytest.fixture
def piece(db, project) -> Content:
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Testing translations",
        slug="testing-translations",
        body_markdown=BODY,
        status=ContentStatus.DRAFT,
    )
    db.add(row)
    db.commit()
    return row


def _model_says(monkeypatch, payload):
    monkeypatch.setattr(
        ai, "json_completion", lambda *a, **kw: (payload, SimpleNamespace(provider="p", model="m"))
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "T", "body_markdown": ""},
        {"title": "T", "body_markdown": "   "},
        {"title": None, "body_markdown": None},
        {"title": "T", "body_markdown": {"a": 1}},
    ],
    ids=["empty", "blank", "whitespace", "null", "object"],
)
def test_an_answer_without_a_body_keeps_the_previous_translation(db, piece, monkeypatch, payload):
    _model_says(monkeypatch, {"title": "Tester les traductions", "body_markdown": GOOD})
    translation.translate(db, piece, "fr")

    _model_says(monkeypatch, payload)
    with pytest.raises(translation.TranslationUnavailable):
        translation.translate(db, piece, "fr")

    db.expire_all()
    row = db.query(ContentTranslation).filter_by(content_id=piece.id, language="fr").one()
    assert row.body_markdown == GOOD.strip()
    assert row.status == TranslationStatus.FAILED
    assert "without a translation" in row.error


def test_the_route_answers_the_retryable_503(client, auth, piece, monkeypatch):
    _model_says(monkeypatch, {"title": "T", "body_markdown": ""})

    resp = client.post(f"/api/v1/content/{piece.id}/translations", headers=auth, json={"language": "fr"})

    assert resp.status_code == 503, resp.text


def test_as_str_does_not_turn_an_object_into_its_repr():
    assert ai.as_str({"a": 1}) == ""
    assert ai.as_str({"a": 1}, default="x") == "x"
    assert ai.as_str(["one", {"a": 1}, "two"]) == "one two"
    assert ai.as_str(42) == "42"
