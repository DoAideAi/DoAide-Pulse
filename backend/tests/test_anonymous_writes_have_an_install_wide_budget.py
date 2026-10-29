"""The anonymous endpoints that write a row have a budget for the whole install.

``POST /subscribers`` (10/minute, 100/hour) and ``POST /feedback`` (5/hour)
were limited per address only, and each accepted call writes a row. From a
pool of addresses either table grew without bound: the subscriber list — real
people's addresses, which an account exports and charts, and from which junk
can only be removed an address at a time — or the operator's feedback inbox.

Each now has a second, install-wide limit beside the per-address one, set
well above any real sign-up or feedback rate. Past it the endpoint answers
429 to everyone until the window moves.
"""
from __future__ import annotations

import pytest

from app.config import Settings, settings


@pytest.fixture
def tight(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_subscribe_global", "3/hour")
    monkeypatch.setattr(settings, "rate_limit_feedback_global", "3/hour")


def _subscribe(client, n, ip):
    return client.post(
        "/api/v1/subscribers",
        json={"email": f"reader{n}@example.com", "source": "embed"},
        headers={"X-Forwarded-For": ip},
    )


def _feedback(client, n, ip):
    return client.post(
        "/api/v1/feedback",
        json={"category": "general", "message": f"Note number {n} about the widget."},
        headers={"X-Forwarded-For": ip},
    )


@pytest.mark.parametrize("send", [_subscribe, _feedback], ids=["subscribers", "feedback"])
def test_many_addresses_together_stop_at_the_install_budget(client, tight, send):
    answers = [send(client, n, f"203.0.113.{n}").status_code for n in range(3)]
    assert 429 not in answers, answers

    assert send(client, 99, "198.51.100.77").status_code == 429


@pytest.mark.parametrize("name", ["rate_limit_subscribe_global", "rate_limit_feedback_global"])
def test_the_budgets_are_validated_settings(name):
    assert "/" in Settings.model_fields[name].default
