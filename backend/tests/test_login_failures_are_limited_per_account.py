"""Failed sign-ins are limited per account, not only per address.

``POST /auth/login`` was limited per client IP (10/minute, 100/hour). That
bounds one machine; it does nothing against guesses spread across many, and a
single-user instance has exactly one account worth guessing at. Failures are
now also counted against the submitted address, in the same storage as every
other limit, and past the budget the address is refused before bcrypt runs.
"""
from __future__ import annotations

import pytest

from app import ratelimit
from app.ratelimit import _LOGIN_FAILURES, login_locked, record_login_failure

LOGIN = "/api/v1/auth/login"
BUDGET = _LOGIN_FAILURES[0].amount


def _login(client, username, password, ip):
    return client.post(
        LOGIN,
        data={"username": username, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def test_failures_from_many_addresses_lock_the_account(client, user):
    for n in range(BUDGET):
        resp = _login(client, user.email, "wrong-password", f"203.0.113.{n % 250}")
        assert resp.status_code == 401, resp.text

    # A fresh IP, and the right password: still refused, because the account
    # has spent its failures for this window.
    resp = _login(client, user.email, "hunter2hunter2", "198.51.100.7")

    assert resp.status_code == 429, resp.text
    assert "failed sign-ins" in resp.json()["detail"]


def test_the_lock_follows_the_address_in_any_case(client, user):
    for n in range(BUDGET):
        _login(client, user.email.upper(), "wrong-password", f"203.0.113.{n}")

    assert login_locked(f"  {user.email}  ")


def test_an_unknown_address_is_locked_the_same_way(client):
    for n in range(BUDGET):
        assert _login(client, "nobody@example.com", "x", f"203.0.113.{n}").status_code == 401

    assert _login(client, "nobody@example.com", "x", "198.51.100.1").status_code == 429


def test_a_successful_sign_in_spends_nothing(client, user):
    for n in range(BUDGET + 5):
        resp = _login(client, user.email, "hunter2hunter2", f"203.0.113.{n}")
        assert resp.status_code == 200, (n, resp.text)
    assert not login_locked(user.email)


def test_one_account_s_failures_do_not_lock_another(client, user):
    for _ in range(BUDGET):
        record_login_failure("someone-else@example.com")

    assert not login_locked(user.email)
    assert _login(client, user.email, "hunter2hunter2", "198.51.100.9").status_code == 200


def test_a_storage_outage_fails_open(monkeypatch, user):
    class _Broken:
        def test(self, *a, **kw):
            raise ConnectionError("redis down")

        hit = test

    monkeypatch.setattr(ratelimit.limiter, "_limiter", _Broken())

    record_login_failure(user.email)  # does not raise
    assert login_locked(user.email) is False


def test_the_counter_store_does_not_hold_the_address():
    key = ratelimit._account_bucket("Owner@Example.com")
    assert "example" not in key.lower()
    assert key == ratelimit._account_bucket(" owner@example.com ")


@pytest.fixture(autouse=True)
def _trust_forwarded_for(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", True)
