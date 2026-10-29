"""Tags the model writes are held to the rule tags a person types are.

Every API write of a tag list goes through ``clean_tags`` (blanks and
invisible characters dropped, a repeat that differs only in case dropped).
``content_from_generated`` — the funnel every generated piece passes — only
clipped them to length. So a model's ``["Python", "python"]`` was stored as
two tags, spent two of a platform's four tag slots on one, and the first
autosave in the editor cleaned them, banking a "tags" revision nobody made.
"""
from __future__ import annotations

from app.models.content import ContentStatus, ContentType
from app.services.content_generator import GeneratedContent, content_from_generated


def _build(db, project, tags):
    generated = GeneratedContent(
        title="Retries", body_markdown="Body " * 200, excerpt="x",
        meta_description="m", tags=tags,
    )
    return content_from_generated(
        db, project_id=project.id, content_type=ContentType.TUTORIAL,
        generated=generated, status=ContentStatus.DRAFT, source={"kind": "test"},
    )


def test_a_repeat_in_another_case_is_dropped(db, project):
    assert _build(db, project, ["Python", "python", "Docker"]).tags == ["Python", "Docker"]


def test_blanks_and_invisible_tags_are_dropped(db, project):
    assert _build(db, project, ["", "  ", "​", "ci"]).tags == ["ci"]


def test_a_bidi_control_is_not_stored(db, project):
    tags = _build(db, project, ["rel‮ease"]).tags
    assert tags and "‮" not in tags[0]


def test_what_the_editor_sends_back_is_not_a_change(db, project):
    """The point of one rule: a piece saved unedited has nothing to bank."""
    from app.schemas.content import clean_tags

    stored = _build(db, project, ["Python", "python", " Docker "]).tags
    assert clean_tags(stored) == stored
