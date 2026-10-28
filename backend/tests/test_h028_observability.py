"""H028 — observability, M11 pass 5.

Two findings:

1. ``mailer.send`` logged SMTP failures without the recipient or subject,
   making it impossible to correlate a failed delivery with a user.
2. ``publishing_service._mark_connection_invalid`` silently changed a
   connection's status to INVALID without any log line, hiding a state
   change that blocks all future publishing for that user+platform.
"""
from __future__ import annotations

import logging
import smtplib

import pytest

from app.config import settings
from app.models.platform_connection import ConnectionStatus
from app.models.publication import Platform
from app.services import mailer, publishing_service
from app.services.errors import clip_error


# ── Finding 1: mailer.send log lines include recipient and subject ── #


class _FakeSMTP:
    """Minimal SMTP double that can be told to explode on send."""

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        self.message = message


class _ExplodingSMTP(_FakeSMTP):
    def send_message(self, message):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")


@pytest.fixture
def _smtp_up(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", False)


@pytest.fixture
def _smtp_broken(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _ExplodingSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", False)


class TestMailerSuccessLogIncludesRecipient:
    """A successful send must log both the subject and the recipient."""

    @pytest.mark.usefixtures("_smtp_up")
    def test_success_log_contains_recipient(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.services.mailer"):
            mailer.send(to="alice@example.com", subject="Weekly digest", body="hi")

        # Masked since C102 M12: which mailbox, not whose.
        assert "a***@example.com" in caplog.text
        assert "alice@example.com" not in caplog.text

    @pytest.mark.usefixtures("_smtp_up")
    def test_success_log_contains_subject(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.services.mailer"):
            mailer.send(to="alice@example.com", subject="Weekly digest", body="hi")

        assert "Weekly digest" in caplog.text


class TestMailerFailureLogIncludesContext:
    """An SMTP failure must log enough to identify which email it was."""

    @pytest.mark.usefixtures("_smtp_broken")
    def test_failure_log_contains_recipient(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.services.mailer"):
            mailer.send(to="bob@example.com", subject="Password reset", body="link")

        assert "b***@example.com" in caplog.text
        assert "bob@example.com" not in caplog.text

    @pytest.mark.usefixtures("_smtp_broken")
    def test_failure_log_contains_subject(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.services.mailer"):
            mailer.send(to="bob@example.com", subject="Password reset", body="link")

        assert "Password reset" in caplog.text

    @pytest.mark.usefixtures("_smtp_broken")
    def test_failure_log_contains_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.services.mailer"):
            mailer.send(to="bob@example.com", subject="s", body="b")

        assert "bad credentials" in caplog.text


# ── Finding 2: _mark_connection_invalid logs the transition ───────── #


CIPHERTEXT = "stored-ciphertext"


@pytest.fixture
def conn(db, user):
    """A real connection row, since the invalidation is a conditional UPDATE."""
    from app.models.platform_connection import PlatformConnection

    row = PlatformConnection(
        user_id=user.id,
        platform=Platform.DEVTO,
        status=ConnectionStatus.CONNECTED,
        encrypted_credentials=CIPHERTEXT,
    )
    db.add(row)
    db.commit()
    return row


class TestMarkConnectionInvalidLogs:
    """Invalidating a connection must leave a WARNING in the journal."""

    def _mark(self, db, user, error="Token rejected"):
        publishing_service._mark_connection_invalid(
            db, user.id, Platform.DEVTO, error, ciphertext=CIPHERTEXT,
        )

    def test_log_contains_platform(self, caplog, db, user, conn):
        with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
            self._mark(db, user)
        assert "devto" in caplog.text

    def test_log_contains_user_id(self, caplog, db, user, conn):
        with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
            self._mark(db, user)
        assert str(user.id) in caplog.text

    def test_log_contains_connection_id(self, caplog, db, user, conn):
        with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
            self._mark(db, user)
        assert f"connection {conn.id} " in caplog.text

    def test_log_contains_error_reason(self, caplog, db, user, conn):
        with caplog.at_level(logging.WARNING, logger="app.services.publishing_service"):
            self._mark(db, user, "Token rejected by platform")
        assert "Token rejected" in caplog.text

    def test_status_is_set_to_invalid(self, db, user, conn):
        self._mark(db, user, "Expired")
        db.commit()
        db.refresh(conn)
        assert conn.status is ConnectionStatus.INVALID

    def test_last_error_is_set(self, db, user, conn):
        self._mark(db, user, "Expired token")
        db.commit()
        db.refresh(conn)
        assert conn.last_error == clip_error("Expired token")
