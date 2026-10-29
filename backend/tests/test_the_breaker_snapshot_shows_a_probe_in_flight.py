"""The breaker snapshot shows a route held by a probe as held, not open for business.

Once a tripped breaker's cool-down ends, ``allow`` hands one caller the probe
and keeps everyone else out until it reports. ``snapshot`` — what every breaker
table on /health/detail and /metrics is built from — still read only the
cool-down: ``seconds_until_retry: 0`` for a route every other caller was being
turned away from. Somebody asking "why is Dev.to being skipped?" was told it
was not.

The hold a probe puts on the route now counts toward ``seconds_until_retry``,
and ``probing`` (1.0 / 0.0, the snapshot is numeric) says one is out.
"""
from __future__ import annotations

import time

from app.services.breaker import CircuitBreaker


def _half_open_with_probe_out() -> CircuitBreaker:
    breaker = CircuitBreaker(threshold=1, cooldown_seconds=60)
    breaker.record_failure("devto:7", now=time.monotonic() - 120)
    assert breaker.allow("devto:7") is True  # the probe goes out
    return breaker


def test_a_probe_in_flight_is_shown_as_holding_the_route():
    entry = _half_open_with_probe_out().snapshot()["devto:7"]

    assert entry["probing"] == 1.0
    assert entry["seconds_until_retry"] > 0


def test_a_closed_route_is_not_probing():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    breaker.record_failure("groq")

    entry = breaker.snapshot()["groq"]

    assert entry["probing"] == 0.0
    assert entry["seconds_until_retry"] == 0.0


def test_handing_the_probe_back_clears_it():
    breaker = _half_open_with_probe_out()
    breaker.release("devto:7")

    assert breaker.snapshot()["devto:7"]["probing"] == 0.0
