"""A translation whose answer arrived but could not be stored is ``failed``.

``translate`` commits the row ``PENDING`` before the model call. Only a provider
error moved it on; anything raised after the answer came back left it pending
for good, and the language list showed "Waiting" with nothing working on it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.content import Content, ContentStatus, ContentType
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


def test_a_failure_after_the_answer_marks_the_row_failed(db, content, monkeypatch):
    completion = SimpleNamespace(provider="p", model="m")
    monkeypatch.setattr(
        ai, "json_completion", lambda *a, **kw: ({"title": "T", "body_markdown": "B"}, completion)
    )

    def _broken(**kwargs):
        raise RuntimeError("validator bug")

    monkeypatch.setattr(translation, "validate", _broken)

    with pytest.raises(RuntimeError):
        translation.translate(db, content, "fr")

    db.expire_all()
    row = db.query(ContentTranslation).filter_by(content_id=content.id, language="fr").one()
    assert row.status == TranslationStatus.FAILED
    assert row.error
    assert "validator bug" not in row.error
