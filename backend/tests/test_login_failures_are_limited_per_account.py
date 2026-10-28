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


# --------------------------------------------------------------------------- #
# Boundaries (C103 M1)                                                         #
# --------------------------------------------------------------------------- #


def test_one_failure_short_of_the_budget_still_signs_in(client, user):
    for n in range(BUDGET - 1):
        assert _login(client, user.email, "wrong", f"203.0.113.{n}").status_code == 401

    assert not login_locked(user.email)
    assert _login(client, user.email, "hunter2hunter2", "198.51.100.2").status_code == 200


def test_the_budget_th_failure_is_the_one_that_locks(client, user):
    for n in range(BUDGET - 1):
        _login(client, user.email, "wrong", f"203.0.113.{n}")
    assert not login_locked(user.email)

    # The last failure the budget allows is still answered as a failure...
    assert _login(client, user.email, "wrong", "203.0.113.250").status_code == 401
    # ...and only the attempt after it is refused unread.
    assert login_locked(user.email)


def test_the_lock_lifts_once_its_window_has_passed(client, user, monkeypatch):
    import time

    from limits import parse_many

    monkeypatch.setattr(ratelimit, "_LOGIN_FAILURES", parse_many("3/1 second"))
    for _ in range(3):
        record_login_failure(user.email)
    assert login_locked(user.email)

    time.sleep(1.1)

    assert not login_locked(user.email)
    assert _login(client, user.email, "hunter2hunter2", "198.51.100.3").status_code == 200


def test_requests_the_ip_limit_refuses_do_not_spend_the_account_s_budget(client, user):
    """The per-IP 429 happens before the handler, so it records no failure.

    Otherwise one noisy client behind a shared address could spend the owner's
    account budget with requests that never had their password read.
    """
    statuses = [
        _login(client, user.email, "wrong", "203.0.113.77").status_code
        for _ in range(BUDGET + 5)
    ]
    assert statuses.count(401) < BUDGET  # the IP limit stepped in first
    assert 429 in statuses

    assert not login_locked(user.email)
    assert _login(client, user.email, "hunter2hunter2", "198.51.100.4").status_code == 200


@pytest.fixture(autouse=True)
def _trust_forwarded_for(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", True)


def test_a_completed_password_reset_lifts_the_lock(client, user, db):
    """A completed reset lifts the lock; signing in with the new password works.

    The 429 no longer suggests a reset — there is no page to start one from
    yet — but a reset done through the API still ends the lockout.
    """
    from app.services import password_reset

    for n in range(BUDGET):
        _login(client, user.email, "wrong-password", f"203.0.113.{n}")
    assert _login(client, user.email, "hunter2hunter2", "198.51.100.7").status_code == 429

    raw = password_reset.issue(db, user)
    resp = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "a-brand-new-passphrase"},
    )
    assert resp.status_code == 200, resp.text

    resp = _login(client, user.email, "a-brand-new-passphrase", "198.51.100.8")
    assert resp.status_code == 200, resp.text


def test_a_failed_reset_does_not_lift_the_lock(client, user):
    for n in range(BUDGET):
        _login(client, user.email, "wrong-password", f"203.0.113.{n}")

    resp = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "x" * 43, "new_password": "a-brand-new-passphrase"},
    )
    assert resp.status_code == 400

    assert login_locked(user.email)


def test_the_lockout_says_how_long_it_lasts_and_offers_no_dead_end(client, user):
    for n in range(BUDGET):
        _login(client, user.email, "wrong-password", f"203.0.113.{n}")

    detail = _login(client, user.email, "hunter2hunter2", "198.51.100.9").json()["detail"]
    assert detail.startswith("Too many failed sign-ins for this account.")
    assert "Try again in" in detail
    assert "minute" in detail or "hour" in detail
    # No page exists to reset a password from; the message must not send people
    # looking for one.
    assert "reset" not in detail.lower()

