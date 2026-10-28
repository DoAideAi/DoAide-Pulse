"""A publisher reads at most 1 MB of a response, and not for ever.

``_capped`` truncated ``resp.content`` — after ``httpx.request`` had already
read every byte. A self-hosted WordPress or Ghost (the adapters pointed at a
host the user typed) answering with gigabytes held all of it in the worker's
heap first. And httpx's ``timeout`` bounds each read, not the response, so a
body dripped a byte at a time under the read timeout held a publish worker for
as long as the server liked. ``_exchange`` streams, stops at the cap, and
raises ``ReadTimeout`` past an overall deadline.
"""
from __future__ import annotations

import contextlib

import httpx
import pytest

from app.services.publishers import base

URL = "https://blog.example.com/wp-json/wp/v2/posts"


def _install(monkeypatch, chunks, *, clock=None):
    pulled: list[int] = []

    def body():
        for index, chunk in enumerate(chunks):
            pulled.append(index)
            if clock is not None:
                clock[0] += 5.0
            yield chunk

    @contextlib.contextmanager
    def fake_stream(method, url, **kwargs):
        assert kwargs["timeout"] == 10
        yield httpx.Response(
            200, content=body(), request=httpx.Request(method, url)
        )

    monkeypatch.setattr(base.httpx, "stream", fake_stream)
    if clock is not None:
        monkeypatch.setattr(base.time, "monotonic", lambda: clock[0])
    return pulled


def test_reading_stops_at_the_cap(monkeypatch):
    def endless():
        while True:
            yield b"x" * 65536

    pulled = _install(monkeypatch, endless())

    response = base._exchange("GET", URL, timeout=10, follow_redirects=False)

    assert len(response.content) == base._MAX_RESPONSE_BYTES
    # The body was never read whole: a few chunks past the cap at most.
    assert len(pulled) <= base._MAX_RESPONSE_BYTES // 65536 + 1


def test_a_slow_drip_is_cut_off_at_the_deadline(monkeypatch):
    clock = [0.0]
    pulled = _install(monkeypatch, (b"x" for _ in range(4096)), clock=clock)

    with pytest.raises(httpx.ReadTimeout):
        base._exchange("POST", URL, timeout=10, follow_redirects=False)

    assert len(pulled) <= 10 * base._DEADLINE_FACTOR // 5 + 1


def test_an_ordinary_response_reads_through(monkeypatch):
    _install(monkeypatch, [b'{"id": ', b"7}"])

    response = base._exchange("POST", URL, timeout=10, follow_redirects=True)

    assert response.status_code == 200
    assert response.json() == {"id": 7}
