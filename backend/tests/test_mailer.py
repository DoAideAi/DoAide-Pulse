"""The SMTP mailer.

No mail server is contacted: ``smtplib.SMTP`` is replaced with a recorder, which
is the only way to assert on STARTTLS and login ordering without one.
"""
from __future__ import annotations

import smtplib
import ssl

import pytest

from app.config import settings
from app.services import mailer


class _FakeSMTP:
    """Records the sequence of calls an SMTP session receives."""

    instances: list[_FakeSMTP] = []

    def __init__(self, host, port, timeout=None, **kwargs):
        self.host, self.port, self.timeout = host, port, timeout
        self.context = kwargs.get("context")
        self.starttls_context = None
        self.calls: list[str] = []
        self.message = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")
        return False

    def starttls(self, **kwargs):
        self.calls.append("starttls")
        self.starttls_context = kwargs.get("context")

    def login(self, user, password):
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, message):
        self.calls.append("send")
        self.message = message


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "pulse@example.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password")
    monkeypatch.setattr(settings, "smtp_from", "Pulse <pulse@example.com>")
    return _FakeSMTP


def test_not_configured_without_a_host():
    assert mailer.configured() is False
    assert mailer.send(to="a@example.com", subject="s", body="b") is False


def test_starttls_then_login_then_send(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)

    assert mailer.send(to="dev@example.com", subject="Reset", body="link") is True

    session = smtp.instances[0]
    # Order matters: credentials must not go out before the channel is encrypted.
    assert session.calls == [
        "starttls",
        "login:pulse@example.com:app-password",
        "send",
        "quit",
    ]
    assert session.message["To"] == "dev@example.com"
    assert session.message["From"] == "Pulse <pulse@example.com>"
    assert session.message["Subject"] == "Reset"
    assert session.message.get_content().strip() == "link"


def test_implicit_tls_does_not_also_starttls(smtp, monkeypatch):
    """STARTTLS on an already-encrypted SMTP_SSL connection is an error."""
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_starttls", True)

    assert mailer.send(to="dev@example.com", subject="s", body="b") is True
    assert "starttls" not in smtp.instances[0].calls


def test_anonymous_relay_skips_login(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    mailer.send(to="dev@example.com", subject="s", body="b")
    assert not any(c.startswith("login") for c in smtp.instances[0].calls)


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPAuthenticationError(535, b"nope"),
        OSError("connection refused"),
        # The recipient refused outright: nothing was delivered.
        smtplib.SMTPRecipientsRefused({"dev@example.com": (550, b"no such user")}),
        # Dropped mid-conversation.
        smtplib.SMTPServerDisconnected("Connection unexpectedly closed"),
        TimeoutError("timed out"),
    ],
    ids=["auth", "refused-connection", "recipient-refused", "disconnected", "timeout"],
)
def test_send_failures_are_reported_not_raised(smtp, monkeypatch, error):
    """The caller answers the same either way, so a raise would only be a 500."""
    def explode(self, message):
        raise error

    monkeypatch.setattr(_FakeSMTP, "send_message", explode)
    assert mailer.send(to="dev@example.com", subject="s", body="b") is False


def test_from_address_falls_back_to_the_login_not_the_relay_s_domain(smtp, monkeypatch):
    """``pulse@<SMTP_HOST>`` forged the relay's domain; see
    test_mail_is_never_sent_from_the_relay_s_own_domain."""
    monkeypatch.setattr(settings, "smtp_from", "")
    mailer.send(to="dev@example.com", subject="s", body="b")
    assert smtp.instances[0].message["From"] == "pulse@example.com"


def test_a_password_smtplib_cannot_encode_fails_like_a_bad_password(smtp, monkeypatch):
    """smtplib encodes the login as ASCII; an accented password raised
    UnicodeEncodeError out of a function documented never to raise (C104 M5)."""

    def login(self, user, password):
        password.encode("ascii")

    monkeypatch.setattr(_FakeSMTP, "login", login, raising=False)
    monkeypatch.setattr(settings, "smtp_password", "pässwörd")

    assert mailer.send(to="dev@example.com", subject="s", body="b") is False


@pytest.mark.parametrize("subject", ["Weekly\r\nBcc: everyone@example.com", "two\nlines"])
def test_a_subject_that_would_inject_a_header_is_refused_not_raised(smtp, subject):
    assert mailer.send(to="dev@example.com", subject=subject, body="b") is False
    assert smtp.instances == []  # nothing was opened


def _verifies(context) -> bool:
    """A context that would refuse a forged certificate for the wrong host."""
    return (
        context is not None
        and context.verify_mode == ssl.CERT_REQUIRED
        and context.check_hostname is True
    )


def test_starttls_checks_the_servers_certificate(smtp, monkeypatch):
    """``starttls()`` with no context uses ``ssl._create_stdlib_context()``,
    which accepts any certificate for any host — so the reset link, a working
    credential, went out over TLS that anyone on the path could terminate."""
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)

    assert mailer.send(to="dev@example.com", subject="Reset", body="link") is True

    assert _verifies(smtp.instances[0].starttls_context)


def test_implicit_tls_checks_the_servers_certificate(smtp, monkeypatch):
    """``SMTP_SSL`` has the same unverified default as ``starttls``."""
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_port", 465)

    assert mailer.send(to="dev@example.com", subject="Reset", body="link") is True

    assert _verifies(smtp.instances[0].context)


# The two headers RFC 5322 makes a message's own business. ``EmailMessage``
# adds neither and ``smtplib.send_message`` does not either; whether the relay
# fills them in is the relay's choice, and Gmail refuses mail without a
# Message-ID outright ("not RFC 5322 compliant"). A reset link that bounces is
# a lockout.
def test_every_message_carries_a_date_and_a_message_id(smtp):
    assert mailer.send(to="dev@example.com", subject="Reset", body="link") is True

    message = smtp.instances[0].message
    assert message["Date"]
    message_id = message["Message-ID"]
    assert message_id and message_id.startswith("<") and message_id.endswith(">")
    # Named for the sending domain, so it is unique and attributable.
    assert message_id.rstrip(">").endswith("@example.com")


def test_message_ids_are_unique(smtp):
    mailer.send(to="a@example.com", subject="One", body="x")
    mailer.send(to="b@example.com", subject="Two", body="y")
    ids = {s.message["Message-ID"] for s in smtp.instances}
    assert len(ids) == 2
