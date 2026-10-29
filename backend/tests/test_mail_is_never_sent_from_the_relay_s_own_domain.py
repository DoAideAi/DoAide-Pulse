"""With SMTP_FROM blank, mail is not sent from the relay's own domain.

``mailer._from_address`` fell back to ``pulse@<SMTP_HOST>``: mail "from"
``pulse@smtp.sendgrid.net`` or ``pulse@smtp.gmail.com``. That forges the relay
operator's domain, receivers check its DMARC policy (the big providers publish
strict ones), and password resets and digests went to junk or were refused —
with nothing in Pulse's log, since the SMTP hop itself succeeded.

The fallback is now the SMTP login when it is an address (what the relay
authenticates, and what providers align on), and then the site's own domain.
"""
from __future__ import annotations

import logging

import pytest

from app.config import settings
from app.services import mailer


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.sendgrid.net")
    monkeypatch.setattr(settings, "smtp_from", "")
    monkeypatch.setattr(settings, "frontend_url", "https://pulse.doaide.com")


def test_an_explicit_from_is_used_as_given(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_from", "Pulse <hello@doaide.com>")
    assert mailer._from_address() == "Pulse <hello@doaide.com>"


def test_the_login_is_used_when_it_is_an_address(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "news@doaide.com")
    assert mailer._from_address() == "news@doaide.com"


def test_otherwise_the_site_s_own_domain_not_the_relay_s(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "apikey")  # SendGrid's literal login

    sender = mailer._from_address()

    assert sender == "pulse@pulse.doaide.com"
    assert "sendgrid" not in sender


def test_production_says_when_the_sender_is_a_guess(smtp, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_user", "apikey")
    monkeypatch.setattr(settings, "environment", "production")

    with caplog.at_level(logging.WARNING, logger="app.services.mailer"):
        mailer._from_address()

    assert "SMTP_FROM" in caplog.text
