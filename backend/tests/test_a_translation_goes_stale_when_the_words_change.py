"""A translation is stale when the words it translated change — not whenever
the piece's row is written.

``is_stale`` compared ``content.version``, the optimistic lock, which moves on
every write. Approving, scheduling and publishing all bump it without touching
a word, so a translation of a draft was stale by the time the publish worker
read it and the destination got English. It now compares a fingerprint of the
four translated fields; rows from before the fingerprint keep the old rule.
"""
from __future__ import annotations

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.translation import ContentTranslation, TranslationStatus, text_fingerprint


@pytest.fixture
def pair(db, project):
    piece = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        status=ContentStatus.DRAFT,
        title="Retries",
        slug="retries",
        body_markdown="How retries work. " * 30,
        excerpt="Retries.",
        meta_description="How retries work.",
    )
    db.add(piece)
    db.commit()
    row = ContentTranslation(
        content_id=piece.id,
        language="fr",
        status=TranslationStatus.READY,
        title="Les relances",
        body_markdown="Comment fonctionnent les relances. " * 20,
        source_version=piece.version,
        source_fingerprint=text_fingerprint(piece),
    )
    db.add(row)
    db.commit()
    return piece, row


def test_a_status_change_leaves_it_current(db, pair):
    piece, row = pair
    for status in (ContentStatus.REVIEW, ContentStatus.APPROVED):
        piece.status = status
        db.commit()

    assert piece.version > row.source_version  # the lock moved...
    assert not row.is_stale(piece)  # ...and the translation is still good


@pytest.mark.parametrize("field", ["title", "body_markdown", "excerpt", "meta_description"])
def test_changing_a_translated_field_makes_it_stale(db, pair, field):
    piece, row = pair
    setattr(piece, field, getattr(piece, field) + " Changed.")
    db.commit()

    assert row.is_stale(piece)


def test_keywords_and_tags_are_not_part_of_it(db, pair):
    piece, row = pair
    piece.keywords = ["new"]
    piece.tags = ["fresh"]
    db.commit()

    assert not row.is_stale(piece)


def test_a_row_from_before_the_fingerprint_keeps_the_version_rule(db, pair):
    piece, row = pair
    row.source_fingerprint = None
    piece.status = ContentStatus.REVIEW
    db.commit()

    assert row.is_stale(piece)
