"""Account security events leave a line in the journal (C105 M11).

Sign-in success and refusal were logged; the other doors to an account were
not. A password-reset request wrote nothing whether or not the address had an
account, so somebody walking a list of addresses to learn which exist left no
trace; a reset tried with a made-up token wrote nothing; and a wrong password
on account erasure — a password check behind a stolen session — wrote nothing
either. Each now does, and none of them writes the email address.
"""
from __future__ import annotations

import logging

import pytest

from app.services import mailer

REQUEST = "/api/v1/auth/password-reset"
CONFIRM = "/api/v1/auth/password-reset/confirm"
ME = "/api/v1/auth/me"


@pytest.fixture(autouse=True)
def no_mail(monkeypatch):
    monkeypatch.setattr(mailer, "send", lambda **kw: True)


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name.startswith("app.")]


def test_a_reset_request_for_an_account_names_the_account(client, user, caplog):
    with caplog.at_level(logging.INFO):
        assert client.post(REQUEST, json={"email": user.email}).status_code == 202

    lines = [m for m in _lines(caplog) if "password reset requested" in m]
    assert len(lines) == 1
    assert f"for user {user.id} from" in lines[0]
    assert user.email not in " ".join(_lines(caplog))


def test_a_reset_request_for_no_account_is_logged_without_the_address(client, caplog):
    with caplog.at_level(logging.INFO):
        assert client.post(REQUEST, json={"email": "nobody@example.com"}).status_code == 202

    lines = _lines(caplog)
    assert any("password reset requested for no active account from" in m for m in lines)
    assert "nobody@example.com" not in " ".join(lines)


def test_a_reset_with_a_made_up_token_is_logged(client, caplog):
    with caplog.at_level(logging.INFO):
        resp = client.post(CONFIRM, json={"token": "x" * 40, "new_password": "long-enough-pw"})

    assert resp.status_code == 400
    assert "password reset with an unknown token" in _lines(caplog)


def test_a_wrong_password_on_erase_is_a_warning(client, auth, user, caplog):
    with caplog.at_level(logging.WARNING):
        resp = client.request("DELETE", ME, headers=auth, json={"password": "not-it"})

    assert resp.status_code == 403
    warnings = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "account erase refused" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert f"for user {user.id} from" in warnings[0]
    assert "wrong password" in warnings[0]
