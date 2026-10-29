"""``DELETE /auth/me`` spends the same per-account password budget as sign-in.

Erasing the account asks for the password again, and checked it with nothing
but the per-IP limit in front. That is exactly the bound the sign-in route's
per-account budget exists because it is not enough for: a stolen session could
guess at the password here from as many addresses as it liked — and kept
guessing while the sign-in form itself was refusing that address, because a
lockout the login had imposed was never consulted here. Every wrong guess
counted for nothing anywhere.

A wrong password here is now a failed sign-in for the account's address, and a
locked address cannot erase the account until the lock lifts.
"""
from __future__ import annotations

from app.ratelimit import _LOGIN_FAILURES, login_locked, record_login_failure

ME = "/api/v1/auth/me"
LOGIN = "/api/v1/auth/login"
BUDGET = _LOGIN_FAILURES[0].amount


def _erase(client, auth, password, ip):
    return client.request(
        "DELETE", ME, json={"password": password}, headers={**auth, "X-Forwarded-For": ip}
    )


def test_wrong_passwords_here_spend_the_account_s_budget(client, auth, user):
    for n in range(BUDGET):
        resp = _erase(client, auth, "wrong-password", f"203.0.113.{n % 250}")
        assert resp.status_code == 403, resp.text

    assert login_locked(user.email)
    signin = client.post(
        LOGIN,
        data={"username": user.email, "password": "hunter2hunter2"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert signin.status_code == 429


def test_a_locked_address_cannot_erase_the_account(client, auth, user, db):
    for _ in range(BUDGET):
        record_login_failure(user.email)

    resp = _erase(client, auth, "hunter2hunter2", "198.51.100.8")

    assert resp.status_code == 429, resp.text
    assert "failed sign-ins" in resp.json()["detail"]
    db.expire_all()
    assert db.get(type(user), user.id) is not None, "the account was erased"


def test_the_right_password_still_erases_it(client, auth, user, db):
    resp = _erase(client, auth, "hunter2hunter2", "198.51.100.9")

    assert resp.status_code == 204, resp.text
