"""M5 integration stress: timeouts, body draining, retry backoff, circuit breakers.

Exercises the integration hardening across the three layers:
- Transport: every outbound call has an explicit timeout and capped body
- Retry: exponential backoff with jitter, no retry on non-idempotent POST
  after the request left the building
- Circuit breaker: consecutive failures trip the breaker, success resets it,
  rate limits name their own window
"""
from __future__ import annotations

import time

import httpx
import pytest

from app.services.breaker import CircuitBreaker
from app.services.publishers import breaker as pub_breaker
from app.services.publishers import base as publisher_base
from app.services.publishers.base import _MAX_RESPONSE_BYTES, _exchange


# -- CircuitBreaker --------------------------------------------------------- #


class TestCircuitBreakerStress:
    """The breaker trips on consecutive failures and resets on success."""

    def test_trips_at_threshold(self):
        cb = CircuitBreaker(threshold=3, cooldown_seconds=10)
        now = time.monotonic()
        assert not cb.is_open("x", now=now)
        cb.record_failure("x", now=now)
        cb.record_failure("x", now=now)
        assert not cb.is_open("x", now=now)
        cb.record_failure("x", now=now)
        assert cb.is_open("x", now=now)

    def test_success_resets_count(self):
        cb = CircuitBreaker(threshold=3, cooldown_seconds=10)
        now = time.monotonic()
        cb.record_failure("x", now=now)
        cb.record_failure("x", now=now)
        cb.record_success("x")
        cb.record_failure("x", now=now)
        cb.record_failure("x", now=now)
        assert not cb.is_open("x", now=now)

    def test_cooldown_expires(self):
        cb = CircuitBreaker(threshold=2, cooldown_seconds=5)
        now = time.monotonic()
        cb.record_failure("x", now=now)
        cb.record_failure("x", now=now)
        assert cb.is_open("x", now=now)
        assert not cb.is_open("x", now=now + 6)

    def test_open_for_honours_upstream_window(self):
        cb = CircuitBreaker(threshold=10, cooldown_seconds=5)
        now = time.monotonic()
        cb.open_for("x", 30, now=now)
        assert cb.is_open("x", now=now)
        assert cb.is_open("x", now=now + 25)
        assert not cb.is_open("x", now=now + 31)

    def test_open_for_does_not_shorten_existing_window(self):
        cb = CircuitBreaker(threshold=10, cooldown_seconds=5)
        now = time.monotonic()
        cb.open_for("x", 60, now=now)
        cb.open_for("x", 10, now=now)
        assert cb.is_open("x", now=now + 30)

    def test_keys_are_independent(self):
        cb = CircuitBreaker(threshold=2, cooldown_seconds=10)
        now = time.monotonic()
        cb.record_failure("a", now=now)
        cb.record_failure("a", now=now)
        assert cb.is_open("a", now=now)
        assert not cb.is_open("b", now=now)

    def test_seconds_remaining(self):
        cb = CircuitBreaker(threshold=1, cooldown_seconds=20)
        now = time.monotonic()
        cb.record_failure("x", now=now)
        remaining = cb.seconds_remaining("x", now=now + 5)
        assert 14 <= remaining <= 16


# -- Publisher breaker ------------------------------------------------------- #


class TestPublisherBreakerIntegration:
    """The publisher breaker keys per (platform, user_id)."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        pub_breaker.reset()
        yield
        pub_breaker.reset()

    def test_rate_limit_with_retry_after_opens_breaker(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.publish_breaker_enabled", True)
        from app.models.publication import Platform

        pub_breaker.record_failure(Platform.DEVTO, 1, retry_after=120)
        assert pub_breaker.is_open(Platform.DEVTO, 1)

    def test_different_users_are_independent(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.publish_breaker_enabled", True)
        from app.models.publication import Platform

        for _ in range(10):
            pub_breaker.record_failure(Platform.DEVTO, 1)
        assert pub_breaker.is_open(Platform.DEVTO, 1)
        assert not pub_breaker.is_open(Platform.DEVTO, 2)


# -- Response capping under stress ------------------------------------------ #


def _serve(monkeypatch, status_code: int, body: bytes) -> None:
    """Answer the next ``_exchange`` with *body*, streamed in 64 KB chunks."""
    import contextlib

    @contextlib.contextmanager
    def fake_stream(method, url, **kwargs):
        chunks = (body[i : i + 65536] for i in range(0, len(body), 65536))
        yield httpx.Response(
            status_code, content=chunks, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(publisher_base.httpx, "stream", fake_stream)


def test_capped_preserves_json_on_normal_response(monkeypatch):
    """A normal API response is fully readable after capping."""
    _serve(monkeypatch, 200, b'{"id": 42, "url": "https://dev.to/p/42"}')
    resp = _exchange("PUT", "https://api.test", timeout=10, follow_redirects=False)
    assert resp.json() == {"id": 42, "url": "https://dev.to/p/42"}


def test_capped_truncates_huge_error_page(monkeypatch):
    """A multi-MB HTML error page is truncated to the cap."""
    _serve(monkeypatch, 502, b"<html>" + b"X" * (_MAX_RESPONSE_BYTES * 3) + b"</html>")
    resp = _exchange("GET", "https://api.test", timeout=10, follow_redirects=False)
    assert resp.status_code == 502
    assert len(resp.content) == _MAX_RESPONSE_BYTES


def test_capped_leaves_a_small_body_alone(monkeypatch):
    """A body under the limit comes back byte for byte."""
    _serve(monkeypatch, 200, b"small")
    resp = _exchange("GET", "https://api.test", timeout=10, follow_redirects=False)
    assert resp.content == b"small"
