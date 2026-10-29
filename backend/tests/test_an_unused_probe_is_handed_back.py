"""A half-open probe that never reached the upstream is handed back, not held.

``CircuitBreaker.allow`` gives a half-open route's one probe to the first
caller and keeps everyone else out until it reports — or, if it never does,
for a full cool-down. Several paths took the probe and then never called the
upstream at all, so the route stayed shut for five minutes over a call that
never happened:

* the LLM sweep, when the request's own time budget ran out just as it reached
  the half-open provider — a healthy provider skipped by every request in the
  process because one of them was late;
* a publish whose route was half-open but which stopped before the platform:
  no connection, credentials that will not decrypt, an adapter that is not
  built — and every other row for that account parked behind it.

``release`` gives the claim back without a verdict: the next caller probes.
"""
from __future__ import annotations

import time

import pytest

from app.models.content import Content, ContentStatus, ContentType
from app.models.publication import Platform, Publication, PublicationStatus
from app.services import llm_router, publishing_service
from app.services.breaker import CircuitBreaker
from app.services.publishers import breaker as publish_breaker


def _tripped(name="p", at=0.0) -> CircuitBreaker:
    b = CircuitBreaker(threshold=1, cooldown_seconds=60)
    b.record_failure(name, now=at)
    return b


def test_release_lets_the_next_caller_probe():
    b = _tripped()
    assert b.allow("p", now=61) is True
    assert b.allow("p", now=62) is False

    b.release("p")

    assert b.allow("p", now=62) is True


def test_release_does_not_close_an_open_route():
    b = _tripped()
    b.release("p")
    assert b.allow("p", now=30) is False


def test_release_on_an_unknown_route_is_harmless():
    CircuitBreaker(threshold=1, cooldown_seconds=60).release("never-seen")


def test_a_sweep_out_of_time_hands_the_provider_back(monkeypatch):
    provider = llm_router.Provider(name="gemini", api_key="k", base_url="https://x/", model="m")
    breaker = CircuitBreaker(threshold=1, cooldown_seconds=60)
    monkeypatch.setattr(llm_router, "breaker", breaker)
    breaker.record_failure("gemini", now=time.monotonic() - 120)  # tripped, cool-down over
    called = []
    monkeypatch.setattr(llm_router, "_call", lambda *a, **k: called.append(1))

    outcome = llm_router._sweep(
        [provider], [{"role": "user", "content": "hi"}],
        model=None, fallback_models=(), temperature=0.1, max_tokens=10, timeout=5,
        deadline=time.monotonic(),  # already spent
    )

    assert called == []
    assert isinstance(outcome, llm_router._Pass)
    assert breaker.allow("gemini") is True, "the unused probe was not handed back"


@pytest.fixture(autouse=True)
def _clean_publish_breaker():
    publish_breaker.reset()
    yield
    publish_breaker.reset()


def test_a_publish_that_never_reached_the_platform_hands_the_route_back(db, project, user):
    content = Content(
        project_id=project.id, content_type=ContentType.TUTORIAL, status=ContentStatus.APPROVED,
        title="T", slug="t", body_markdown="Body.",
    )
    db.add(content)
    db.commit()
    publication = Publication(
        content_id=content.id, platform=Platform.DEVTO, status=PublicationStatus.PENDING
    )
    db.add(publication)
    db.commit()
    name = publish_breaker.key(Platform.DEVTO, user.id)
    publish_breaker.breaker.record_failure(name, now=time.monotonic() - 10_000)
    for _ in range(publish_breaker.breaker.threshold):
        publish_breaker.breaker.record_failure(name, now=time.monotonic() - 10_000)

    # No connection for dev.to on this account: the attempt stops before the platform.
    publishing_service.execute(db, publication)

    assert publish_breaker.allow(Platform.DEVTO, user.id) is True
