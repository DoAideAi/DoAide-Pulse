"""Password-reset emails to one address are limited, whoever asks for them.

``POST /auth/password-reset`` was limited per client IP (5/hour), and every
request for a real address issued a token and sent it an email. So anyone
with a few addresses could fill an account owner's inbox with reset emails
from Pulse's domain — spending the sending reputation the reset link itself
depends on — and, because each new token revokes the one before it, keep
killing the link the real owner was trying to use.

The address now has a budget of its own beside the per-IP one. Past it the
answer is the same 202 (whether an address has an account is not something
this endpoint tells anyone), but nothing is issued and nothing is sent.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.models.password_reset import PasswordResetToken
from app.ratelimit import _RESET_REQUESTS

URL = "/api/v1/auth/password-reset"
BUDGET = _RESET_REQUESTS[0].amount


@pytest.fixture
def outbox(monkeypatch):
    from app.routers import auth as auth_router

    sent: list[str] = []
    monkeypatch.setattr(auth_router, "_send_reset_email", lambda to, s, b: sent.append(to))
    return sent


def _ask(client, email, ip):
    return client.post(URL, json={"email": email}, headers={"X-Forwarded-For": ip})


def test_many_addresses_asking_for_one_inbox_stop_at_its_budget(client, user, db, outbox):
    for n in range(BUDGET + 3):
        resp = _ask(client, user.email, f"203.0.113.{n}")
        assert resp.status_code == 202, resp.text

    assert len(outbox) == BUDGET
    assert db.query(PasswordResetToken).filter_by(user_id=user.id).count() == BUDGET


def test_past_the_budget_the_answer_does_not_change(client, user, outbox):
    answers = {
        _ask(client, user.email, f"198.51.100.{n}").json()["detail"] for n in range(BUDGET + 2)
    }
    assert len(answers) == 1


def test_one_address_s_budget_is_not_another_s(client, user, db, outbox):
    from app.models.user import User
    from app.security import hash_password

    other = User(email="other@example.com", hashed_password=hash_password("other-pass-123"))
    db.add(other)
    db.commit()
    for n in range(BUDGET):
        _ask(client, user.email, f"203.0.113.{n}")

    _ask(client, other.email, "192.0.2.10")

    assert outbox.count(other.email) == 1


def test_the_budget_is_a_validated_setting():
    assert settings.rate_limit_password_reset_per_account


def test_a_storage_outage_does_not_stop_resets(monkeypatch):
    from app import ratelimit

    class _Broken:
        def hit(self, *a, **kw):
            raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit.limiter, "_limiter", _Broken())

    assert ratelimit.reset_request_allowed("someone@example.com") is True


def test_with_the_limiter_off_nothing_is_counted(monkeypatch):
    from app import ratelimit

    monkeypatch.setattr(ratelimit.limiter, "enabled", False)

    assert all(ratelimit.reset_request_allowed("x@example.com") for _ in range(BUDGET + 5))
