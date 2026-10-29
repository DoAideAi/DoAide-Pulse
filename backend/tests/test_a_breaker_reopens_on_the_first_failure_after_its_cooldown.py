"""After its cool-down a tripped breaker lets one call probe, and reopens if it fails.

The breaker counted consecutive failures, tripped at ``threshold``, reset the
count to zero and opened for the cool-down. When the cool-down ran out it was
closed in every sense: the next ``threshold`` calls all went to an upstream
that was still down, each one waiting out its full timeout (thirty seconds for
the idea generator, the whole retry budget for a publish), before it opened
again. Every cycle of an outage spent that much again.

A breaker that has tripped is now half-open after its cool-down: the first
failure reopens it at once, and a success closes it as before.
"""
from __future__ import annotations

from app.services.breaker import CircuitBreaker


def _tripped(breaker, name="gemini", at=0.0):
    for _ in range(breaker.threshold):
        breaker.record_failure(name, now=at)
    assert breaker.is_open(name, now=at)


def test_the_first_failure_after_the_cooldown_reopens_it():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    _tripped(breaker)

    after = 61.0
    assert not breaker.is_open("gemini", now=after), "the probe is let through"
    assert breaker.record_failure("gemini", now=after) is True
    assert breaker.is_open("gemini", now=after + 1)


def test_a_success_after_the_cooldown_closes_it_for_good():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    _tripped(breaker)

    assert breaker.record_success("gemini") is True
    # Closed: back to needing a full run of failures.
    breaker.record_failure("gemini", now=200)
    breaker.record_failure("gemini", now=200)
    assert not breaker.is_open("gemini", now=200)


def test_a_breaker_that_never_tripped_still_needs_the_full_threshold():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    breaker.record_failure("groq", now=0)
    breaker.record_failure("groq", now=0)
    assert not breaker.is_open("groq", now=0)


def test_reopening_waits_a_full_cooldown_again():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    _tripped(breaker)
    breaker.record_failure("gemini", now=61)
    assert breaker.is_open("gemini", now=120)
    assert not breaker.is_open("gemini", now=122)
