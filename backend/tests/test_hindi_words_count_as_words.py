"""A Hindi or Tamil word is a word, to tag suggestions and to duplicate checks.

The tokenizer was ``[0-9a-z]+``. A Hindi headline had no words, so a repeat of
it was never caught (empty tokens are "not a duplicate") and the autopilot
could write the same Hindi idea again; a Hindi article offered no words to
suggest as tags; and a Hindi tag the account already used never matched one.
"""
from __future__ import annotations

from app.models.content import Content, ContentStatus, ContentType
from app.services import dedup


def test_devanagari_and_tamil_words_survive_whole():
    # Vowel signs (combining marks) stay attached to their letters.
    assert dedup.words("हिंदी समाचार: नई रिलीज़") == ["हिंदी", "समाचार", "नई", "रिलीज़"]
    assert dedup.words("தமிழ் செய்தி") == ["தமிழ்", "செய்தி"]


def test_the_english_rules_are_unchanged():
    assert dedup.words("Pulse 2.0 fixes a double-post bug") == [
        "pulse", "2.0", "fixes", "a", "double-post", "bug",
    ]


def test_a_reworded_hindi_headline_is_caught_as_a_repeat():
    first = dedup.tokens("पल्स संस्करण दो रिलीज़ हुआ नई सुविधाएं")
    assert first
    assert dedup.is_restatement("पल्स संस्करण दो रिलीज़ हुआ नई सुविधाएं आज", first)
    assert not dedup.is_restatement("डेटाबेस बैकअप कैसे लें पूरी गाइड", first)


def _piece(db, project, title, body, tags=None):
    row = Content(
        project_id=project.id,
        content_type=ContentType.TUTORIAL,
        title=title,
        slug=f"p-{abs(hash(title)) % 10_000}",
        status=ContentStatus.DRAFT,
        body_markdown=body,
        tags=tags or [],
    )
    db.add(row)
    db.commit()
    return row


def _suggested(client, auth, piece):
    resp = client.post(f"/api/v1/tags/suggest/{piece.id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return {s["tag"] for s in resp.json()}


def test_a_hindi_article_gets_its_frequent_words_suggested(client, auth, db, project):
    body = "क्रिकेट " * 4 + "आज का मैच रोमांचक था।"
    piece = _piece(db, project, "आज का खेल", body)

    assert "क्रिकेट" in _suggested(client, auth, piece)


def test_a_hindi_tag_the_account_uses_is_matched_in_a_hindi_article(client, auth, db, project):
    _piece(db, project, "पुराना लेख", "पहले लिखा गया। " * 5, tags=["राजनीति"])
    piece = _piece(db, project, "नया लेख", "आज की राजनीति पर बात।")

    assert "राजनीति" in _suggested(client, auth, piece)
