"""Two requests to translate a piece into the same language at once.

Both found no ``(piece, language)`` row, both inserted one, and
``uq_translation_per_language`` failed the second commit — an unhandled
``IntegrityError``, so a double-click on "Translate" came back as a 500. The
loser is now a 409 that names what is happening, and it makes no model call:
the winner is already paying for one.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation
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
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title="Testing translations",
        slug="testing-translations",
        body_markdown=BODY,
        status=ContentStatus.DRAFT,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lost_race(db, content, monkeypatch):
    """The other request's row is committed; this one's lookup ran before it."""
    db.add(ContentTranslation(content_id=content.id, language="fr"))
    db.commit()
    monkeypatch.setattr(translation, "get", lambda *a, **kw: None)
    monkeypatch.setattr(
        ai, "json_completion", lambda *a, **kw: pytest.fail("the loser called the model")
    )


def test_the_loser_is_told_it_is_in_progress(db, content, lost_race):
    with pytest.raises(translation.TranslationInProgress):
        translation.translate(db, content, "fr")

    # The session is usable afterwards, and the winner's row is untouched.
    assert db.query(ContentTranslation).filter_by(content_id=content.id).count() == 1


def test_the_api_answers_409(client, auth, content, lost_race):
    resp = client.post(
        f"/api/v1/content/{content.id}/translations",
        headers=auth,
        json={"language": "fr"},
    )

    assert resp.status_code == 409, resp.text
    assert "already being translated" in resp.json()["detail"]
