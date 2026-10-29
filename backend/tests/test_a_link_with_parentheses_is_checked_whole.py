"""A URL with parentheses in it is checked whole, not up to its first ")".

The extractor's Markdown pattern could not match a link whose address holds a
parenthesis, so the bare-URL fallback took over and stopped at the first
``)``. A Wikipedia link — ``…/wiki/Python_(programming_language)`` — was
checked as ``…/wiki/Python_(programming_language``, which does not exist,
reported dead, and the publish refused with a 409 over a link that works.
"""
from __future__ import annotations

import time

import pytest

from app.services.link_check import extract_urls

WIKI = "https://en.wikipedia.org/wiki/Python_(programming_language)"


@pytest.mark.parametrize(
    "body",
    [
        f"Read [about Python]({WIKI}) first.",
        f"Read [about Python]({WIKI} \"the article\") first.",
        f"Bare: {WIKI} works too.",
        f"Bare at the end of a sentence: {WIKI}.",
    ],
)
def test_the_whole_address_is_extracted(body):
    assert extract_urls(body) == [WIKI]


def test_a_parenthesis_that_belongs_to_the_sentence_is_still_dropped():
    assert extract_urls("Pulse (see https://example.com/docs) is fine.") == [
        "https://example.com/docs"
    ]


def test_a_link_inside_parentheses_ends_at_its_own_paren():
    assert extract_urls("([docs](https://example.com/docs)) and more") == [
        "https://example.com/docs"
    ]


def test_a_hostile_run_of_parentheses_is_still_fast():
    """The pattern's classes stay disjoint, so no quadratic backtracking."""
    body = "[x](https://e.com/" + "(" * 20000 + " " + ")" * 20000
    start = time.perf_counter()
    extract_urls(body)
    assert time.perf_counter() - start < 1.0
