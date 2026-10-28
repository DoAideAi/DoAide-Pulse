"""What a long-form adapter sends is the piece as written (C104 M2).

Each adapter's outgoing payload is captured at ``_request`` and searched for
the parts of a body most likely to be mangled on the way: accented, CJK and
emoji text (flags and ZWJ sequences included), ``&`` and ``<`` in prose and in
code, HTML inside a fenced code block, a table, a long unbroken word, and the
last line — which is what goes first when something truncates. Medium and
WordPress send HTML, so an entity-encoded form of a marker counts as present.
"""
from __future__ import annotations

import html
import json

import pytest

from app.services.publishers.base import PREFLIGHT_ERROR, PublishError, PublishRequest
from app.services.publishers.buttondown import ButtondownAdapter
from app.services.publishers.devto import DevToAdapter
from app.services.publishers.hashnode import HashnodeAdapter
from app.services.publishers.medium import MediumAdapter
from app.services.publishers.wordpress import WordPressAdapter

LONG_WORD = "Supercalifragilistic" * 20
TITLE = "Ünïcödé “quotes” & <tags> — 🇮🇳 中文"
BODY = (
    "Intro with café, naïve, 中文字符, 🇮🇳 and 👨‍👩‍👧, AT&T, a < b > c.\n\n"
    "## Code\n\n```html\n<script>alert('x')</script>\n```\n\n"
    "Inline `a && b`.\n\n| col | 中 |\n|---|---|\n| 1 | 🙂 |\n\n"
    + LONG_WORD
    + "\n\nLast line ✅ END-MARKER"
)
MARKERS = [
    "café", "naïve", "中文字符", "🇮🇳", "👨‍👩‍👧", "AT&T", "alert('x')",
    "a && b", "🙂", "✅", "END-MARKER", LONG_WORD,
]
CREDENTIALS = {
    "api_key": "k", "publication_id": "p", "integration_token": "t",
    "site_url": "https://wp.example.com", "username": "u", "application_password": "p",
}


def _sent(adapter, monkeypatch) -> str:
    """Everything the adapter put in a request body, as one string."""
    bodies: list = []

    class _Empty:
        status_code = 201
        headers: dict = {}

        def json(self):
            return {}

    def capture(method, url, **kwargs):
        bodies.append(kwargs.get("json_body"))
        return _Empty()

    monkeypatch.setattr(adapter, "_request", capture)
    request = PublishRequest(
        title=TITLE, body_markdown=BODY, excerpt="Ex", meta_description="Meta", tags=["python"]
    )
    # The empty answer is refused after the send; the send is what is checked.
    with pytest.raises(PublishError):
        adapter.publish(request, CREDENTIALS)
    assert bodies, "nothing was sent"
    return json.dumps(bodies, ensure_ascii=False)


@pytest.mark.parametrize(
    "adapter",
    [DevToAdapter, HashnodeAdapter, MediumAdapter, WordPressAdapter, ButtondownAdapter],
    ids=lambda a: a.__name__,
)
def test_the_body_and_title_arrive_whole(adapter, monkeypatch):
    sent = _sent(adapter(), monkeypatch)
    for marker in MARKERS:
        assert marker in sent or html.escape(marker, quote=False) in sent, marker
    assert TITLE in sent or html.escape(TITLE, quote=False) in sent


def test_a_title_dev_to_will_refuse_is_reported_before_publishing():
    def findings(title):
        return [
            f for f in DevToAdapter().preflight(
                PublishRequest(title=title, body_markdown="b", excerpt="", meta_description="")
            )
            if f.level == PREFLIGHT_ERROR
        ]

    assert findings("x" * 128) == []
    [finding] = findings("x" * 129)
    assert "128" in finding.message and finding.actual == 129
