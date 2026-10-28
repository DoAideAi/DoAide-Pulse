"""A 429 says which limit was hit and how long until it lifts (C103 M19).

It said "slow down and try again shortly" while the same response's
Retry-After header held the answer — so the person reading the toast was the
one party not told how long "shortly" was.
"""
from __future__ import annotations

import pytest
from limits import parse

from app import ratelimit
from app.config import settings


@pytest.fixture(autouse=True)
def _trust_forwarded_for(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", True)


def test_a_rate_limited_login_names_the_limit_and_the_wait(client):
    resp = None
    for _ in range(30):
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "someone@example.com", "password": "nope"},
            headers={"X-Forwarded-For": "198.51.100.200"},
        )
        if resp.status_code == 429:
            break
    assert resp is not None and resp.status_code == 429
    detail = resp.json()["detail"]
    assert "limited to 10 per minute" in detail
    assert "Try again in" in detail
    # The sentence and the header agree: the wait it names is the header's,
    # rounded up to a unit (a fresh one-minute window reads "1 minute").
    wait = int(resp.headers["Retry-After"])
    assert 0 <= wait <= 60
    assert ratelimit._describe_wait(wait) in detail or "1 minute" in detail


@pytest.mark.parametrize(
    ("limit", "said"),
    [("10/minute", "10 per minute"), ("100/hour", "100 per hour"), ("5/3 hours", "5 per 3 hours")],
)
def test_a_limit_reads_as_a_sentence(limit, said):
    assert ratelimit._describe_limit(parse(limit)) == said


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0.2, "1 second"),
        (1, "1 second"),
        (42.1, "43 seconds"),
        (60, "1 minute"),
        (61, "2 minutes"),
        (3599, "1 hour"),
        (3600, "1 hour"),
        (7201, "3 hours"),
    ],
)
def test_a_wait_is_rounded_up_to_a_unit_a_person_reads(seconds, said):
    assert ratelimit._describe_wait(seconds) == said


def test_no_limit_on_the_request_keeps_the_old_sentence():
    assert ratelimit.too_many_requests_detail(None).startswith("Too many requests")
