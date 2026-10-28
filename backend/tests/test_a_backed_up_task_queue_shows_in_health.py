"""A task queue that is backing up shows in the health check (C105 M11).

A worker that answers ``ping`` while one slow generation holds it left every
probe green: the database and Redis were up, a worker replied, and publications
were not yet late. Scans, webhooks and triggers piled up in the broker behind it
with nothing anywhere saying so. ``/health/detail`` now reports the broker's
queue length as ``queue`` — ``ok``, ``behind`` past a warning line (and logged),
``unknown`` if the broker cannot be read, ``disabled`` when tasks run inline.
"""
from __future__ import annotations

import logging

import pytest
import redis

from app.config import settings
from app.routers import misc

URL = "/api/v1/health/detail"


@pytest.fixture
def celery_on(monkeypatch):
    monkeypatch.setattr(settings, "celery_enabled", True)
    monkeypatch.setattr(misc, "_check_redis", lambda: misc._Probe(True))
    monkeypatch.setattr(misc, "_check_workers", lambda: misc._Probe(True))


def _broker(monkeypatch, waiting):
    """Stand in for the broker, so no test talks to a real Redis."""
    asked: list[str] = []

    class _Client:
        def llen(self, name):
            asked.append(name)
            if isinstance(waiting, Exception):
                raise waiting
            return waiting

        def close(self):
            pass

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url, **kw: _Client()))
    return asked


def _queue(client, auth):
    resp = client.get(URL, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_tasks_run_inline_means_no_queue(client, auth):
    assert _queue(client, auth)["queue"]["status"] == "disabled"


def test_a_short_queue_is_ok_and_says_how_long(client, auth, celery_on, monkeypatch):
    asked = _broker(monkeypatch, 3)
    body = _queue(client, auth)
    assert body["queue"] == {"status": "ok", "required": False, "detail": "3 tasks waiting"}
    assert asked == ["celery"]


def test_a_long_queue_is_behind_logged_and_not_a_503(
    client, auth, celery_on, monkeypatch, caplog
):
    _broker(monkeypatch, settings.health_queue_backlog_warn + 50)
    caplog.set_level(logging.WARNING)

    body = _queue(client, auth)

    assert body["queue"]["status"] == "behind"
    assert body["queue"]["detail"].startswith(
        f"{settings.health_queue_backlog_warn + 50} tasks waiting"
    )
    assert "pulse-worker" in body["queue"]["detail"]
    # Reported, not folded into the overall status — like the worker probe.
    assert body["status"] == "ok"
    assert any("task queue is behind" in r.getMessage() for r in caplog.records)


def test_a_broker_that_cannot_be_read_is_unknown_not_a_500(
    client, auth, celery_on, monkeypatch, caplog
):
    _broker(monkeypatch, redis.ConnectionError("refused"))
    caplog.set_level(logging.WARNING)

    body = _queue(client, auth)

    assert body["queue"]["status"] == "unknown"
    assert body["queue"]["detail"] == "ConnectionError"
    assert any("queue probe failed" in r.getMessage() for r in caplog.records)
