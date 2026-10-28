"""A breaker that closes says so (C105 M11).

Both breakers logged a WARNING when they opened and nothing when the upstream
came back, so the journal could say when a platform or provider went out and
never when it returned — and how long the outage lasted was a question nobody
could answer from it. The success that closes a tripped circuit is now an INFO
line; a success with no outage behind it writes nothing.
"""
from __future__ import annotations

import logging

import pytest

from app.config import settings
from app.models.publication import Platform
from app.services import llm_router, user_llm
from app.services.breaker import CircuitBreaker
from app.services.publishers import breaker as publish_breaker
from tests.conftest import TestSession


def test_the_breaker_reports_which_success_closed_a_circuit():
    b = CircuitBreaker(threshold=2, cooldown_seconds=0)
    assert b.record_success("a") is False          # never failed
    b.record_failure("a")
    assert b.record_success("a") is False          # counting, never open
    b.record_failure("a")
    b.record_failure("a")                          # tripped
    assert b.record_success("a") is True
    assert b.record_success("a") is False          # already closed


def test_a_publishing_route_that_recovers_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(settings, "publish_breaker_enabled", True)
    publish_breaker.reset()
    for _ in range(settings.publish_breaker_threshold):
        publish_breaker.record_failure(Platform.DEVTO, 7)

    with caplog.at_level(logging.INFO, logger=publish_breaker.__name__):
        publish_breaker.record_success(Platform.DEVTO, 7)
        publish_breaker.record_success(Platform.DEVTO, 7)

    lines = [r.getMessage() for r in caplog.records if "breaker closed" in r.getMessage()]
    assert lines == [f"publishing breaker closed for {publish_breaker.key(Platform.DEVTO, 7)} — the platform answered again"]
    publish_breaker.reset()


class _Resp:
    status_code = 200
    headers: dict = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}


@pytest.fixture
def one_provider(monkeypatch):
    llm_router.breaker.reset()
    monkeypatch.setattr(user_llm, "session_factory", TestSession)
    for name in ("openrouter", "gemini", "groq", "cerebras"):
        monkeypatch.setattr(settings, f"{name}_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(llm_router, "_post", lambda url, **kw: _Resp())
    yield
    llm_router.breaker.reset()


def test_an_llm_provider_that_recovers_is_logged(one_provider, caplog):
    llm_router.breaker.open_for("openrouter", 0)  # tripped, cool-down already over

    with caplog.at_level(logging.INFO, logger=llm_router.__name__):
        llm_router.complete([{"role": "user", "content": "hi"}])
        llm_router.complete([{"role": "user", "content": "hi"}])

    lines = [r.getMessage() for r in caplog.records if "breaker closed" in r.getMessage()]
    assert lines == ["llm breaker closed for openrouter — it answered again"]
