"""After its cool-down a tripped breaker lets *one* caller probe, not all of them.

Half-open was a state only ``record_failure`` knew about. ``is_open`` answered
False to every caller from the moment the cool-down ran out until the first
failure came back — and the first failure comes back a full timeout later. So
every request that arrived in that window went to the upstream that had just
been down: the whole publish queue for an account at once, each row spending an
attempt, or every visitor to the idea generator waiting out thirty seconds.

The gates now ask ``allow``, which hands the probe to the first caller and
keeps the route shut for the rest until that probe reports, or until a full
cool-down passes without it reporting (a probe that died must not wedge the
route shut for good).
"""
from __future__ import annotations

from app.services.breaker import CircuitBreaker


def _tripped(name="devto:7", at=0.0) -> CircuitBreaker:
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    for _ in range(3):
        breaker.record_failure(name, now=at)
    return breaker


def test_only_the_first_caller_after_the_cooldown_is_let_through():
    breaker = _tripped()

    assert breaker.allow("devto:7", now=61) is True
    assert breaker.allow("devto:7", now=61.5) is False
    assert breaker.allow("devto:7", now=70) is False


def test_the_others_are_told_to_wait_out_the_probe():
    breaker = _tripped()
    breaker.allow("devto:7", now=61)

    assert breaker.seconds_remaining("devto:7", now=61) > 0


def test_a_successful_probe_opens_the_route_to_everyone():
    breaker = _tripped()
    breaker.allow("devto:7", now=61)
    breaker.record_success("devto:7")

    assert breaker.allow("devto:7", now=62) is True
    assert breaker.allow("devto:7", now=62) is True


def test_a_failed_probe_reopens_for_a_full_cooldown_then_probes_again():
    breaker = _tripped()
    breaker.allow("devto:7", now=61)
    assert breaker.record_failure("devto:7", now=65) is True

    assert breaker.allow("devto:7", now=100) is False
    assert breaker.allow("devto:7", now=126) is True
    assert breaker.allow("devto:7", now=126) is False


def test_a_probe_that_never_reports_does_not_shut_the_route_for_good():
    breaker = _tripped()
    breaker.allow("devto:7", now=61)

    assert breaker.allow("devto:7", now=122) is True


def test_a_closed_breaker_allows_everyone():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    breaker.record_failure("groq", now=0)

    assert all(breaker.allow("groq", now=1) for _ in range(5))


def test_an_open_breaker_allows_nobody():
    breaker = _tripped()

    assert breaker.allow("devto:7", now=30) is False


def test_the_publish_queue_sends_one_row_into_a_recovering_platform(monkeypatch):
    """The gate in ``publishing_service.execute`` asks ``allow``, not ``is_open``."""
    from app.models.publication import Platform
    from app.services.publishers import breaker as publish_breaker

    publish_breaker.reset()
    try:
        name = publish_breaker.key(Platform.DEVTO, 7)
        for _ in range(publish_breaker.breaker.threshold):
            publish_breaker.breaker.record_failure(name, now=0)
        clock = publish_breaker.breaker.cooldown + 1
        monkeypatch.setattr("app.services.breaker.time.monotonic", lambda: clock)

        let_through = [publish_breaker.allow(Platform.DEVTO, 7) for _ in range(5)]
        assert let_through == [True, False, False, False, False]
    finally:
        publish_breaker.reset()
