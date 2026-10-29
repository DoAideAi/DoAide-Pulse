"""Log lines written inside a thread pool keep the request id they belong to.

The request id lives in a context variable, and ``RequestIdFilter`` stamps it
on every record. Starlette's threadpool copies context into its threads;
``concurrent.futures.ThreadPoolExecutor`` does not. Five services fan work out
through one — the link checker, the meta audit, the sitemap sweep, both Umami
views — and every line they log from inside the pool said ``request_id=-``:
the link checker's "SSRF-blocked url=…" warning, the one line saying a
published piece linked somewhere Pulse refused to fetch, could not be tied to
the publish or the request that caused it.

``logging_config.carrying_context`` wraps the pooled function so each call
runs in a copy of the caller's context.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.logging_config import carrying_context, request_id_var
from app.services import link_check


class _Recorder(logging.Handler):
    """What the request id was, in the thread that logged, at the moment it logged."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.ids: list[tuple[str, str]] = []

    def emit(self, record):
        self.ids.append((record.getMessage(), request_id_var.get()))


def test_carrying_context_takes_the_request_id_into_the_pool():
    token = request_id_var.set("req-abc123")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            seen = list(pool.map(carrying_context(lambda _: request_id_var.get()), range(4)))
    finally:
        request_id_var.reset(token)

    assert seen == ["req-abc123"] * 4


def test_a_bare_pool_does_not_which_is_the_bug():
    token = request_id_var.set("req-abc123")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            seen = pool.submit(request_id_var.get).result()
    finally:
        request_id_var.reset(token)

    assert seen != "req-abc123"


def test_the_link_checker_s_warning_carries_the_request_id():
    recorder = _Recorder()
    logger = logging.getLogger("app.services.link_check")
    logger.addHandler(recorder)
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    token = request_id_var.set("req-publish-42")
    try:
        link_check.check(["http://127.0.0.1/internal", "http://10.0.0.1/admin"])
    finally:
        request_id_var.reset(token)
        logger.removeHandler(recorder)
        logger.setLevel(previous)

    blocked = [rid for message, rid in recorder.ids if "SSRF-blocked" in message]
    assert blocked, recorder.ids
    assert set(blocked) == {"req-publish-42"}
