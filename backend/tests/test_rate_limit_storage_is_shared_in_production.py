"""Rate-limit counters must be shared by the API's workers in production.

The API runs two uvicorn workers. In-memory counters are per process, so with
``RATE_LIMIT_STORAGE_URI`` blank every limit was doubled — the login
brute-force budget included — and reset on each restart. Production only got
it right because its ``.env`` set the variable; ``.env.example`` leaves it blank.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app import ratelimit
from app.config import settings
from app.ratelimit import storage_uri


def _config(**overrides):
    base = {
        "rate_limit_storage_uri": "",
        "is_production": True,
        "redis_url": "redis://localhost:6379/0",
    }
    return SimpleNamespace(**{**base, **overrides})


def test_an_explicit_uri_always_wins():
    assert storage_uri(_config(rate_limit_storage_uri="redis://cache:6379/3")) == (
        "redis://cache:6379/3"
    )


def test_production_without_one_shares_the_redis_it_already_has():
    assert storage_uri(_config()) == "redis://localhost:6379/0"


def test_development_keeps_process_memory():
    assert storage_uri(_config(is_production=False)) == "memory://"


def test_production_with_no_redis_at_all_says_so(caplog):
    with caplog.at_level(logging.WARNING, logger="app.ratelimit"):
        assert storage_uri(_config(redis_url="")) == "memory://"
    assert any("per worker process" in r.getMessage() for r in caplog.records)


# --- A hung Redis costs a request half a second, not a TCP timeout (M10) --- #


@pytest.mark.parametrize(
    "uri",
    ["redis://localhost:6379/0", "rediss://cache.example.com:6380/3", "unix:///run/redis.sock"],
)
def test_a_redis_store_is_given_socket_timeouts(uri):
    timeout = settings.rate_limit_storage_timeout_seconds
    assert ratelimit.storage_options(uri) == {
        "socket_connect_timeout": timeout,
        "socket_timeout": timeout,
    }


def test_memory_storage_is_given_no_redis_options():
    # ``memory://`` refuses keyword options it does not know.
    assert ratelimit.storage_options("memory://") == {}


def test_the_timeout_follows_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_storage_timeout_seconds", 1.5)
    assert ratelimit.storage_options("redis://x:6379/0")["socket_timeout"] == 1.5


def test_a_blackholed_redis_fails_inside_the_timeout():
    """The case the options exist for: no refusal, no answer.

    10.255.255.1 is unroutable on an ordinary network, so the connect neither
    succeeds nor is refused — without a timeout this call sat for over a minute.
    """
    import time

    from limits.storage import storage_from_string

    uri = "redis://10.255.255.1:6379/0"
    storage = storage_from_string(uri, **ratelimit.storage_options(uri))
    started = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - TimeoutError or ConnectionError
        storage.incr("pulse/probe", 60)
    assert time.monotonic() - started < settings.rate_limit_storage_timeout_seconds * 6
