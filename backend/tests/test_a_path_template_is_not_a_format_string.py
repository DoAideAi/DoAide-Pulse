"""A git destination's path template is substituted by name, not by ``str.format``.

``path_template`` comes from the connection form, and ``GitAdapter.path_for``
ran it through ``str.format`` — whose mini-language is not substitution.
``{slug:>999999999}`` asked a worker for a gigabyte of padding on every
publish (the ``.strip()`` after it hid the result, not the cost);
``{slug.upper}`` committed a file named ``<built-in method upper of str object
at 0x…>``; ``{slug!r}`` put quotes in the filename. Only the four documented
placeholders are filled now, and anything else in braces is refused.
"""
from __future__ import annotations

import inspect

import pytest

from app.services.publishers.base import CredentialError, PublishRequest
from app.services.publishers.git import GitAdapter


@pytest.fixture
def request_() -> PublishRequest:
    fields = inspect.signature(PublishRequest).parameters
    values = {k: None for k, f in fields.items() if f.default is inspect.Parameter.empty}
    values.update(title="Launch", body_markdown="Body", slug="pulse-2-0")
    return PublishRequest(**values)


@pytest.mark.parametrize(
    "template",
    [
        "{slug:>999999999}.md",
        "{slug.__class__}.md",
        "{slug.upper}.md",
        "{slug!r}.md",
        "{0}.md",
        "{nope}.md",
        "{slug[0]}.md",
    ],
)
def test_format_language_is_refused(request_, template):
    with pytest.raises(CredentialError, match="placeholder"):
        GitAdapter().path_for(request_, {"path_template": template})


@pytest.mark.parametrize(
    "template, expected",
    [
        ("src/content/blog/{slug}.md", "src/content/blog/pulse-2-0.md"),
        ("content/posts/{slug}/index.md", "content/posts/pulse-2-0/index.md"),
        ("posts/{slug}.md", "posts/pulse-2-0.md"),
    ],
)
def test_the_documented_placeholders_still_fill(request_, template, expected):
    assert GitAdapter().path_for(request_, {"path_template": template}) == expected


def test_a_dated_layout_still_fills(request_):
    path = GitAdapter().path_for(request_, {"path_template": "_posts/{year}-{month}-{day}-{slug}.md"})
    assert path.startswith("_posts/2") and path.endswith("-pulse-2-0.md")
