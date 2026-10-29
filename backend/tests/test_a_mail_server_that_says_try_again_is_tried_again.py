"""A mail server's "try again" (a 4xx) gets one more try, not a lost email.

``mailer.send`` made one attempt and returned ``False`` on any failure. SMTP's
4xx replies are the server saying *this is temporary, come back*: ``421`` busy
or rate-limited, ``450``/``451`` greylisting, which is routine at providers. A
dropped connection mid-session is the same kind of thing. For the password
reset that meant the person was told to check their inbox and nothing arrived,
with no retry anywhere — the reset path is designed to answer before the send
and log the failure.

One more attempt now follows a short pause, for those failures only. A ``5xx``
is the server saying no, and is not repeated; connection refused and timeouts
are an outage, which the digest sweep already hands to Celery's own retry, and
repeating each of those per message would only stack up timeouts.
"""
from __future__ import annotations

import smtplib

import pytest

from app.config import settings
from app.services import mailer


class _Script:
    """An SMTP class whose sessions fail in a scripted order."""

    def __init__(self, failures):
        self.failures = list(failures)
        self.sessions = 0
        self.sent = 0

    def __call__(self, host, port, timeout=None, **kwargs):
        script = self

        class _Session:
            def __enter__(self):
                script.sessions += 1
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self, **kwargs):
                pass

            def login(self, user, password):
                pass

            def send_message(self, message):
                if script.failures:
                    raise script.failures.pop(0)
                script.sent += 1

        return _Session()


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(mailer, "RETRY_PAUSE_SECONDS", 0)

    def install(*failures):
        script = _Script(failures)
        monkeypatch.setattr(smtplib, "SMTP", script)
        monkeypatch.setattr(smtplib, "SMTP_SSL", script)
        return script

    return install


def _send():
    return mailer.send(to="a@example.com", subject="Reset your password", body="link")


@pytest.mark.parametrize(
    "transient",
    [
        smtplib.SMTPResponseException(421, b"too many connections, try later"),
        smtplib.SMTPDataError(451, b"greylisted, try again"),
        smtplib.SMTPServerDisconnected("Connection unexpectedly closed"),
    ],
    ids=["421", "451", "disconnected"],
)
def test_a_temporary_refusal_is_tried_once_more(smtp, transient):
    script = smtp(transient)

    assert _send() is True
    assert (script.sessions, script.sent) == (2, 1)


def test_a_permanent_refusal_is_not_repeated(smtp):
    script = smtp(smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")}))

    assert _send() is False
    assert script.sessions == 1


def test_a_server_that_keeps_saying_later_is_given_up_on(smtp):
    script = smtp(
        smtplib.SMTPResponseException(421, b"later"),
        smtplib.SMTPResponseException(421, b"still later"),
    )

    assert _send() is False
    assert script.sessions == 2


def test_an_outage_is_not_retried_per_message(smtp, monkeypatch):
    calls = {"n": 0}

    def refused(*args, **kwargs):
        calls["n"] += 1
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(smtplib, "SMTP", refused)

    assert _send() is False
    assert calls["n"] == 1


def test_a_recipient_deferred_with_a_4xx_is_tried_again(smtp):
    script = smtp(smtplib.SMTPRecipientsRefused({"a@example.com": (450, b"mailbox busy")}))

    assert _send() is True
    assert script.sessions == 2
