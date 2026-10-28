"""A tag suggestion's reason states how often the word really appears.

Title words weigh triple when ranking, and that weight was the number quoted:
a word written once, in the title, was proposed as "Used 3 times in this
piece" — exactly ``MIN_TERM_FREQUENCY``, so it qualified on the weight alone.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType


def _suggest(client, auth, db, project, *, title, body):
    content = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title=title,
        slug="piece",
        status=ContentStatus.DRAFT,
        body_markdown=body,
    )
    db.add(content)
    db.commit()
    resp = client.post(f"/api/v1/tags/suggest/{content.id}", headers=auth)
    assert resp.status_code == 200
    return {s["tag"]: s["reason"] for s in resp.json()}


def test_a_word_only_in_the_title_is_not_said_to_be_used_three_times(client, auth, db, project):
    reasons = _suggest(client, auth, db, project, title="Kubernetes notes", body="Short body.")
    assert reasons["kubernetes"] == "In the title, and used once in this piece."


def test_title_and_body_mentions_are_added_once_each(client, auth, db, project):
    reasons = _suggest(
        client, auth, db, project, title="Caching guide", body="caching " * 4 + "done."
    )
    assert reasons["caching"] == "In the title, and used 5 times in this piece."


def test_a_body_only_word_reads_as_before(client, auth, db, project):
    reasons = _suggest(client, auth, db, project, title="Notes", body="redis " * 3)
    assert reasons["redis"] == "Used 3 times in this piece."
