"""Saving and reading a piece costs time linear in its length, whatever it contains.

The markdown helpers that run on every save and every ``GET /content/{id}`` —
the excerpt, word count, SEO audit, quality report, link extraction and fact
check — used patterns like ``\\[([^\\]]*)\\]\\([^)]*\\)``. Each ``[`` scanned to
the end of the body before failing (``[^\\]]*`` happily eats further ``[``), as
did each ``](`` looking for ``)``, and the fact check's address arm ``\\S+@``
scanned an unbroken token from every one of its positions. A 200,000-character
body of ``[`` took 88 seconds to save and 88 more to *read*. No class now
admits the character that opens it, and the address arm starts only at a token.
"""
from __future__ import annotations

import time

import pytest

from app.models.content import BODY_MARKDOWN_MAX_LENGTH
from app.services import factcheck, link_check, quality, seo

L = BODY_MARKDOWN_MAX_LENGTH
#: Generous. These were 5–90 seconds before; they are milliseconds now.
BUDGET_SECONDS = 3.0

ATTACKS = {
    "open-brackets": "[" * (L - 1) + "x",
    "unclosed-links": "[a](" * (L // 4),
    "bracket-paren-runs": "](" * (L // 2),
    "image-openers": "![" * (L // 2),
    "unbroken-token": "x" * L,
    "at-signs": "a@" * (L // 2),
}


@pytest.mark.parametrize("body", list(ATTACKS.values()), ids=list(ATTACKS))
@pytest.mark.parametrize(
    "helper",
    [
        seo.strip_markdown,
        quality.prose_lines,
        lambda b: link_check._MD_LINK.findall(b),
        lambda b: seo._IMG_ALT.findall(b),
        lambda b: factcheck._LINK_TARGET.sub(" ", b),
    ],
    ids=["strip_markdown", "prose_lines", "link_extract", "img_alt", "factcheck_targets"],
)
def test_each_helper_is_fast_on_hostile_bodies(helper, body):
    started = time.monotonic()
    helper(body)
    assert time.monotonic() - started < BUDGET_SECONDS


@pytest.mark.parametrize("body", [ATTACKS["open-brackets"], ATTACKS["unclosed-links"]], ids=["brackets", "links"])
def test_saving_and_reading_such_a_piece_is_fast(client, auth, project, body):
    started = time.monotonic()
    created = client.post(
        "/api/v1/content",
        headers=auth,
        json={"project_id": project.id, "content_type": "announcement", "title": "T", "body_markdown": body},
    )
    read = client.get(f"/api/v1/content/{created.json()['id']}", headers=auth)

    assert created.status_code == 201 and read.status_code == 200
    assert time.monotonic() - started < 2 * BUDGET_SECONDS


def test_ordinary_markdown_still_reads_the_same():
    body = "See [the docs](https://x.y/a) and ![logo](https://x.y/i.png). Mail ann@example.com."
    assert seo.strip_markdown(body) == "See the docs and . Mail ann@example.com."
    assert link_check._MD_LINK.findall(body) == ["https://x.y/a", "https://x.y/i.png"]
    assert seo._IMG_ALT.findall(body) == ["logo"]
    assert "ann@example.com" not in factcheck._LINK_TARGET.sub(" ", body)
    assert quality.prose_lines("# Head\n\n- see [docs](https://x)\n") == ["Head", "see docs"]
