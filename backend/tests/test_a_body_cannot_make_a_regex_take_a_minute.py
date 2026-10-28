"""Body-shaped input runs the regular expressions in linear time.

Three patterns that read article bodies (up to 200,000 characters, written by
the user or by a model whose prompt quotes other people's text) were
quadratic on one shape of input each:

* ``seo_autofix._BODY_LINK`` admitted ``[`` in a link's text, so a body of
  opening brackets scanned to its end from every one of them (~80 s);
* ``translation._FENCE`` used ``\\s*`` under MULTILINE, which crosses newlines,
  so a run of blank lines did the same (~60 s);
* ``ai.extract_json_object`` stripped fences with ``\\s*```$`` tried from every
  position in a run of whitespace.

The bound below is loose on purpose — two seconds against a minute — so it
fails on the shape of the algorithm, never on a slow machine.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.services import ai, seo_autofix, translation

BODY_LIMIT = 200_000


def _quick(fn, *args) -> None:
    started = time.perf_counter()
    fn(*args)
    assert time.perf_counter() - started < 2.0, f"{fn.__name__} is not linear"


@pytest.mark.parametrize("shape", ["[", "[a", "[](", "!["])
def test_links_are_found_in_linear_time(shape):
    _quick(seo_autofix._body_links, shape * (BODY_LIMIT // len(shape)))


def test_links_are_still_found():
    body = "See [the docs](https://example.com/docs) and ![a picture](/i.png)."
    assert seo_autofix._body_links(body) == ["https://example.com/docs"]


def test_fences_are_counted_in_linear_time():
    _quick(translation._FENCE.findall, "\n" * BODY_LIMIT)
    _quick(translation._FENCE.findall, " \n" * (BODY_LIMIT // 2))


def test_fences_are_still_counted():
    body = "Intro\n\n```python\nx = 1\n```\n\n   ```\nindented\n   ```\n"
    assert len(translation._FENCE.findall(body)) == 4


@pytest.mark.parametrize("filler", [" ", "\n", " \t"])
def test_a_reply_full_of_whitespace_is_read_in_linear_time(filler):
    reply = '{"title": "x"' + filler * (BODY_LIMIT // len(filler)) + "}"
    _quick(ai.extract_json_object, reply)


@pytest.mark.parametrize(
    "reply",
    ['```json\n{"title": "Fenced"}\n```', '```\n{"title": "Fenced"}\n```', '{"title": "Fenced"}'],
)
def test_a_fenced_reply_is_still_unwrapped(reply):
    assert ai.extract_json_object(reply) == {"title": "Fenced"}


def test_the_translation_check_still_compares_fences():
    source = SimpleNamespace(body_markdown="```\ncode\n```\n")
    assert len(translation._FENCE.findall(source.body_markdown)) == 2
