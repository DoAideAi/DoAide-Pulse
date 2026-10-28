"""A feed served a trickle at a time is abandoned, not waited on.

``_read_capped`` capped the size of a feed but not the time spent reading it:
httpx's timeout is per read, so a URL that answered and then sent a few bytes
every few seconds — under the read timeout every time — held the poller for
as long as it took to reach the 5 MB cap. The whole download now has a budget.
"""
from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services import feeds


def test_a_trickled_feed_is_a_feed_error(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(feeds.time, "monotonic", lambda: clock[0])
    pulled: list[int] = []

    def trickle():
        for n in range(10_000):
            pulled.append(n)
            clock[0] += settings.feed_timeout_seconds / 2
            yield b"<"

    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=trickle()))
    )

    with pytest.raises(feeds.FeedError, match="too long"):
        feeds._read_capped(client, "https://example.com/feed.xml")

    assert len(pulled) <= feeds.FEED_DEADLINE_FACTOR * 2 + 1


def test_a_prompt_feed_reads_through():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<rss/>"))
    )
    assert feeds._read_capped(client, "https://example.com/feed.xml") == b"<rss/>"
