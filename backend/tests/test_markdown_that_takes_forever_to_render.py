"""Bodies built to make the Markdown renderer quadratic render in linear time.

python-markdown's inline link pattern looks for a closing ``]`` from every
unmatched ``[`` (and for a ``)`` from every ``](``), and its code-span pattern
does the same from a long run of backticks. 8,000 ``[`` took six and a half
seconds; a body at the 200,000-character limit would have held a worker for
about an hour on every publish, preview and plain-text conversion — and
``to_html`` is behind all of them. ``formatting._defuse`` swaps those
characters for private-use stand-ins the parser treats as letters, and puts
them back after rendering, so the output is identical.
"""
from __future__ import annotations

import time

import pytest

from app.models.content import BODY_MARKDOWN_MAX_LENGTH
from app.services.publishers import formatting

L = BODY_MARKDOWN_MAX_LENGTH
#: Generous: each of these took minutes before, and well under a second after.
BUDGET_SECONDS = 5.0


@pytest.mark.parametrize(
    "body",
    [
        "[" * (L - 1) + "x",
        "[a" * (L // 2),
        "![" * (L // 2),
        "[a](" * (L // 4),
        "`" * L,
        "a " + "`" * (L - 2),
    ],
    ids=["open-brackets", "bracket-letter", "image-openers", "unclosed-link-targets",
         "backtick-run", "backtick-run-after-text"],
)
def test_a_pathological_body_at_the_size_limit_renders_quickly(body):
    started = time.monotonic()
    html = formatting.to_html(body)
    elapsed = time.monotonic() - started

    assert elapsed < BUDGET_SECONDS, f"{elapsed:.1f}s"
    assert "" not in html and "" not in html and "" not in html


def test_the_output_is_what_the_characters_say():
    body = "x " + "[" * 100 + " y " + "`" * 40
    assert formatting.to_html(body) == "<p>x " + "[" * 100 + " y " + "`" * 40 + "</p>"


@pytest.mark.parametrize(
    "body",
    [
        "# Title\n\nSee [the docs](https://x.y) and [ref][1].\n\n[1]: https://z\n",
        "```\na[0] = `x`\nfor (i in [1,2,3]) {}\n```\n",
        "Use ```` around a fence.\n\n````\n```\nx\n```\n````\n",
        "A [lone bracket and a (paren in prose.",
    ],
)
def test_ordinary_documents_are_not_touched(body):
    assert formatting._defuse(body) == body


def test_brackets_inside_a_fence_are_left_alone_even_in_bulk():
    fenced = "```\n" + "[" * 500 + "\n```\n"
    assert formatting._defuse(fenced) == fenced
    assert "[" * 500 in formatting.to_html(fenced)


def test_private_use_characters_in_the_input_cannot_impersonate_a_stand_in():
    html = formatting.to_html("ab " + "[" * 100)
    assert "a[b" not in html
    assert "" not in html
