"""Rate-limit counters must be shared by the API's workers in production.

The API runs two uvicorn workers. In-memory counters are per process, so with
``RATE_LIMIT_STORAGE_URI`` blank every limit was doubled — the login
brute-force budget included — and reset on each restart. Production only got
it right because its ``.env`` set the variable; ``.env.example`` leaves it blank.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

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
