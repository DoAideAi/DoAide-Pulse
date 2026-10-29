"""Listing a piece's translations costs the same with two languages as with ten.

``translation.listing`` loads only the columns a picker needs; when
``source_fingerprint`` arrived (a6f73c2) it was not among them, so the
``is_stale`` each row runs lazy-loaded it — one extra query per language.
"""
from __future__ import annotations

from sqlalchemy import event

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation, TranslationStatus, text_fingerprint
from tests.conftest import engine

LANGS = ["fr", "de", "es", "it", "pt", "nl", "ja", "ko", "zh", "hi"]


def _count(client, auth, url) -> int:
    seen = [0]

    def tick(*_args):
        seen[0] += 1

    event.listen(engine, "before_cursor_execute", tick)
    try:
        assert client.get(url, headers=auth).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", tick)
    return seen[0]


def test_the_translation_list_does_not_grow_a_query_per_language(client, auth, db, project):
    piece = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.DRAFT,
        title="Retries",
        slug="retries",
        body_markdown="How retries work. " * 50,
    )
    db.add(piece)
    db.commit()
    url = f"/api/v1/content/{piece.id}/translations"

    def add(langs):
        for code in langs:
            db.add(
                ContentTranslation(
                    content_id=piece.id,
                    language=code,
                    status=TranslationStatus.READY,
                    title="t",
                    body_markdown="b",
                    source_version=piece.version,
                    source_fingerprint=text_fingerprint(piece),
                )
            )
        db.commit()
        db.expire_all()

    add(LANGS[:2])
    two = _count(client, auth, url)
    add(LANGS[2:])
    ten = _count(client, auth, url)

    assert ten == two, f"{two} queries for 2 languages, {ten} for 10"
